"""FastAPI web application for Drone Acoustic Intelligence."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config import settings
from models.schemas import RecordingMetadata, UploadedFileInfo
from utils.file_utils import (
    analysis_output_dir,
    analysis_upload_dir,
    ensure_runtime_directories,
    is_supported_audio_filename,
    new_analysis_id,
    resolve_artifact,
    resolve_dataset_file,
    save_upload,
)
from utils.logging_utils import logger
from utils.media import extract_audio_to_wav, is_supported_video_filename
from utils.validation import load_microphone_config
from station.router import router as station_router


ensure_runtime_directories()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Offline WAV/MP3/M4A drone acoustic analysis, classification and TDOA localization.",
)
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")

templates = Jinja2Templates(directory=settings.template_dir)
app.include_router(station_router)


def artifact_url(path: str) -> str:
    """Return URL for viewing a generated artifact."""

    return f"/artifact?path={quote(path)}"


def download_url(path: str) -> str:
    """Return URL for downloading a generated artifact."""

    return f"/download?path={quote(path)}"


def dataset_image_url(path: str) -> str:
    """Return URL for a class reference image stored under the dataset dir."""

    return f"/dataset/image?path={quote(path)}"


def _attach_image_urls(summary):
    """Convert each label summary's raw image path into a servable URL."""

    for item in summary.labels:
        if item.image_url:
            item.image_url = dataset_image_url(item.image_url)
    return summary


templates.env.globals["artifact_url"] = artifact_url
templates.env.globals["download_url"] = download_url
templates.env.globals["dataset_image_url"] = dataset_image_url

single_service = None
localization_service = None
dataset_manager = None


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Render the main page."""

    return templates.TemplateResponse(request, "index.html")


@app.get("/single", response_class=HTMLResponse)
async def single_upload_page(request: Request) -> HTMLResponse:
    """Render single-file analysis upload page."""

    return templates.TemplateResponse(request, "single_upload.html")



def _parse_time_intervals(value: str | None) -> list[tuple[float, float]] | None:
    """Parse comma-separated target intervals like ``12.5-28, 41-56``."""

    text = _clean_text(value)
    if not text:
        return None
    intervals: list[tuple[float, float]] = []
    for item in text.replace(";", ",").split(","):
        part = item.strip().replace("–", "-").replace("—", "-")
        if not part:
            continue
        try:
            left, right = part.split("-", 1)
            a, b = float(left.strip()), float(right.strip())
        except Exception as exc:
            raise ValueError(f"Неверный интервал цели: {item!r}. Используйте 12.5-28,41-56") from exc
        if a < 0 or b <= a:
            raise ValueError(f"Неверный интервал цели: {item!r}")
        intervals.append((a, b))
    return intervals or None

def _form_float(value: str | None) -> float | None:
    """Parse an optional numeric form field ('' -> None)."""

    if value is None:
        return None
    value = value.strip()
    return float(value) if value else None


def _clean_text(value: str | None) -> str | None:
    """Trim a text form field; empty string becomes None."""

    if value is None:
        return None
    value = value.strip()
    return value or None


def _render_dataset(request, manager, message=None, result=None, evaluation=None) -> HTMLResponse:
    """Render the dataset page with image URLs attached to each class."""

    summary = _attach_image_urls(manager.summary())
    return templates.TemplateResponse(
        request,
        "dataset.html",
        {"summary": summary, "message": message, "result": result, "evaluation": evaluation},
    )


@app.get("/dataset", response_class=HTMLResponse)
async def dataset_page(request: Request) -> HTMLResponse:
    """Render labeled sound dataset management page."""

    return _render_dataset(request, _get_dataset_manager())


@app.post("/dataset/add", response_class=HTMLResponse)
async def add_dataset_audio(
    request: Request,
    label: str = Form(...),
    audio_files: list[UploadFile] = File(default=[]),
    video_files: list[UploadFile] = File(default=[]),
    label_image: UploadFile | None = File(None),
    window_seconds: float = Form(settings.ml_window_seconds),
    hop_seconds: float = Form(settings.ml_hop_seconds),
    category: str = Form("background"),
    is_drone: bool = Form(False),
    distance_min_m: str | None = Form(None),
    distance_max_m: str | None = Form(None),
    background: str | None = Form(None),
    flight_mode: str | None = Form(None),
    notes: str | None = Form(None),
    target_intervals: str | None = Form(None),
    target_present_full_recording: bool = Form(False),
    auto_train: bool = Form(False),
) -> HTMLResponse:
    """Add labeled audio/video and metadata to the dataset (optionally train)."""

    manager = _get_dataset_manager()
    try:
        clean_label = manager.normalize_label(label)
        if not clean_label:
            raise ValueError("Введите название класса.")

        audio_list = [f for f in audio_files if f and f.filename]
        video_list = [f for f in video_files if f and f.filename]
        has_image = bool(label_image and label_image.filename)
        if not audio_list and not video_list and not has_image:
            raise ValueError("Загрузите аудио, видео или изображение класса.")

        category = category if category in ("drone", "background") else "background"
        training_intervals = _parse_time_intervals(target_intervals) if category == "drone" else None
        if category == "drone" and not training_intervals and not target_present_full_recording:
            raise ValueError(
                "Для записи БПЛА укажите интервалы, где цель реально слышна, "
                "либо явно отметьте, что БПЛА присутствует всю запись. "
                "Полная запись больше не размечается как БПЛА автоматически."
            )
        dataset_role = "research" if clean_label in settings.ml_provisional_labels else "training"
        metadata = RecordingMetadata(
            category=category,
            is_drone=bool(is_drone) or category == "drone",
            distance_min_m=_form_float(distance_min_m),
            distance_max_m=_form_float(distance_max_m),
            background=_clean_text(background),
            flight_mode=_clean_text(flight_mode),
            notes=_clean_text(notes),
            dataset_role=dataset_role,
        )

        results = []
        for audio_file in audio_list:
            if not is_supported_audio_filename(audio_file.filename):
                raise ValueError(
                    f"{audio_file.filename}: не поддерживаемый аудиоформат (WAV, MP3, M4A, AAC)."
                )
            target_dir = manager.raw_label_dir(clean_label) / new_analysis_id()
            saved = await save_upload(audio_file, target_dir)
            results.append(
                manager.add_recording(
                    label=clean_label,
                    source_file=saved,
                    window_seconds=window_seconds,
                    hop_seconds=hop_seconds,
                    metadata=metadata,
                    include_intervals=training_intervals,
                )
            )

        for video_file in video_list:
            if not is_supported_video_filename(video_file.filename):
                raise ValueError(
                    f"{video_file.filename}: не поддерживаемый видеоформат (MP4, MOV, MKV, AVI, M4V, WEBM)."
                )
            target_dir = manager.raw_label_dir(clean_label) / new_analysis_id()
            saved_video = await save_upload(video_file, target_dir)
            wav_path = extract_audio_to_wav(Path(saved_video.stored_path), target_dir)
            wav_info = UploadedFileInfo(
                original_name=f"{video_file.filename} (звук)",
                stored_path=str(wav_path),
                size_bytes=wav_path.stat().st_size,
            )
            results.append(
                manager.add_recording(
                    label=clean_label,
                    source_file=wav_info,
                    window_seconds=window_seconds,
                    hop_seconds=hop_seconds,
                    metadata=metadata,
                    include_intervals=training_intervals,
                )
            )

        image_message = ""
        if has_image:
            image_dir = manager.raw_label_dir(clean_label) / "_uploads"
            saved_image = await save_upload(label_image, image_dir)
            manager.add_label_image(clean_label, saved_image)
            image_message = " Изображение класса сохранено."

        windows_added = sum(item.windows_added for item in results)
        files_added = sum(item.files_added for item in results)
        message = f"Добавлено файлов: {files_added}, окон: {windows_added}.{image_message}"

        evaluation = None
        if auto_train and windows_added:
            train_result = manager.classifier.train()
            message += f" Обучение: {train_result.message}"
            if train_result.trained:
                evaluation = manager.evaluate()
    except Exception as exc:
        logger.exception("Adding dataset audio failed")
        return _error_response(request, exc)

    return _render_dataset(request, manager, message=message, result=results, evaluation=evaluation)


@app.post("/dataset/train", response_class=HTMLResponse)
async def train_dataset_model(request: Request) -> HTMLResponse:
    """Train the local audio-cluster model and estimate its accuracy."""

    manager = _get_dataset_manager()
    result = manager.classifier.train()
    evaluation = manager.evaluate() if result.trained else None
    return _render_dataset(request, manager, message=result.message, result=result, evaluation=evaluation)


@app.post("/dataset/delete", response_class=HTMLResponse)
async def delete_dataset_entry(
    request: Request,
    label: str = Form(...),
    source_file: str | None = Form(None),
) -> HTMLResponse:
    """Delete a whole class or a single recording from the dataset."""

    manager = _get_dataset_manager()
    try:
        source = _clean_text(source_file)
        if source:
            result = manager.delete_source(label, source)
        else:
            result = manager.delete_label(label)
    except Exception as exc:
        logger.exception("Deleting dataset entry failed")
        return _error_response(request, exc)
    return _render_dataset(request, manager, message=result.message, result=result)


@app.get("/dataset/image", name="dataset_image")
async def dataset_image(path: str) -> FileResponse:
    """Serve a class reference image stored inside the dataset directory."""

    return FileResponse(resolve_dataset_file(path))


@app.post("/single/analyze", response_class=HTMLResponse)
async def analyze_single(request: Request, wav_file: UploadFile = File(...)) -> HTMLResponse:
    """Handle single audio upload and render analysis result."""

    try:
        report = await _run_single_analysis(wav_file)
    except Exception as exc:
        logger.exception("Single-file analysis failed")
        return _error_response(request, exc)
    return templates.TemplateResponse(
        request,
        "single_result.html",
        {"report": report},
    )


@app.post("/api/analyze-single")
async def analyze_single_api(wav_file: UploadFile = File(...)) -> JSONResponse:
    """REST endpoint for single audio analysis."""

    try:
        report = await _run_single_analysis(wav_file)
    except Exception as exc:
        logger.exception("Single-file API analysis failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(report.model_dump())


@app.get("/api/dataset")
async def dataset_summary_api() -> JSONResponse:
    """Return labeled dataset and model status."""

    manager = _get_dataset_manager()
    return JSONResponse(manager.summary().model_dump())


@app.post("/api/dataset/train")
async def train_dataset_model_api() -> JSONResponse:
    """Train the local audio-cluster model through the API."""

    manager = _get_dataset_manager()
    result = manager.classifier.train()
    return JSONResponse(result.model_dump())


@app.get("/localization", response_class=HTMLResponse)
async def localization_upload_page(request: Request) -> HTMLResponse:
    """Render localization upload page."""

    return templates.TemplateResponse(request, "localization_upload.html")


@app.post("/localization/analyze", response_class=HTMLResponse)
async def analyze_localization(
    request: Request,
    wav_files: list[UploadFile] = File(...),
    mics_json: UploadFile = File(...),
) -> HTMLResponse:
    """Handle multi-microphone upload and render localization result."""

    try:
        report = await _run_localization_analysis(wav_files, mics_json)
    except Exception as exc:
        logger.exception("Localization analysis failed")
        return _error_response(request, exc)
    return templates.TemplateResponse(
        request,
        "localization_result.html",
        {"report": report},
    )


@app.post("/api/localize")
async def analyze_localization_api(
    wav_files: list[UploadFile] = File(...),
    mics_json: UploadFile = File(...),
) -> JSONResponse:
    """REST endpoint for multi-microphone localization."""

    try:
        report = await _run_localization_analysis(wav_files, mics_json)
    except Exception as exc:
        logger.exception("Localization API analysis failed")
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(report.model_dump())


@app.get("/artifact", name="artifact")
async def artifact(path: str) -> FileResponse:
    """Return a generated artifact for inline display."""

    artifact_path = resolve_artifact(path)
    return FileResponse(artifact_path)


@app.get("/download", name="download")
async def download(path: str) -> FileResponse:
    """Return a generated artifact as a download."""

    artifact_path = resolve_artifact(path)
    return FileResponse(
        artifact_path,
        media_type="application/octet-stream",
        filename=artifact_path.name,
    )


async def _run_single_analysis(wav_file: UploadFile):
    """Save a single audio upload and run the analysis service."""

    global single_service

    if not is_supported_audio_filename(wav_file.filename):
        raise ValueError("Please upload a WAV, MP3 or M4A file.")

    if single_service is None:
        from audio.analyzer import AudioAnalysisService

        single_service = AudioAnalysisService()

    analysis_id = new_analysis_id()
    upload_dir = analysis_upload_dir(analysis_id)
    output_dir = analysis_output_dir(analysis_id)
    saved = await save_upload(wav_file, upload_dir)
    return single_service.analyze(analysis_id, saved, output_dir)


async def _run_localization_analysis(
    wav_files: list[UploadFile],
    mics_json: UploadFile,
):
    """Save localization uploads and run the localization service."""

    global localization_service

    if not mics_json.filename or Path(mics_json.filename).name != "mics.json":
        raise ValueError("Please upload mics.json with microphone coordinates.")
    if not wav_files:
        raise ValueError("Please upload at least two WAV, MP3 or M4A files.")

    if localization_service is None:
        from localization.localizer import LocalizationAnalysisService

        localization_service = LocalizationAnalysisService()

    analysis_id = new_analysis_id()
    upload_dir = analysis_upload_dir(analysis_id)
    output_dir = analysis_output_dir(analysis_id)

    saved_wavs = []
    for upload in wav_files:
        if not is_supported_audio_filename(upload.filename):
            raise ValueError(f"{upload.filename or 'file'} is not a supported audio file (WAV, MP3, M4A or AAC).")
        saved_wavs.append(await save_upload(upload, upload_dir))

    saved_json = await save_upload(mics_json, upload_dir)
    config = load_microphone_config(Path(saved_json.stored_path))
    return localization_service.analyze(
        analysis_id=analysis_id,
        config=config,
        uploaded_files=saved_wavs,
        output_dir=output_dir,
    )


def _error_response(request: Request, exc: Exception) -> HTMLResponse:
    """Render an error page."""

    return templates.TemplateResponse(
        request,
        "error.html",
        {"message": str(exc)},
        status_code=400,
    )


def _get_dataset_manager():
    """Return the singleton sound dataset manager."""

    global dataset_manager

    if dataset_manager is None:
        from ml.dataset import SoundDatasetManager

        dataset_manager = SoundDatasetManager()
    return dataset_manager
