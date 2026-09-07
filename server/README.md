# Мухоед

Мухоед is an offline FastAPI application for acoustic UAV analysis. It analyzes WAV and MP3 recordings, extracts DSP features, classifies the most likely UAV profile with a transparent expert system, builds an acoustic passport, and estimates source position and trajectory from multiple microphones with GCC-PHAT/TDOA.

The first version intentionally does not use a neural network. The classifier is rule-based and easy to extend with new acoustic profiles or replace later with an ML model.

## Features

- Single WAV/MP3 analysis.
- DC removal, peak normalization and sample-rate warnings.
- FFT, STFT spectrogram, Mel spectrogram and waveform processing.
- Fundamental frequency, harmonic count, harmonic spacing and stability.
- RMS, average energy, zero crossing rate, spectral centroid, spectral bandwidth, spectral flatness and MFCC.
- 6-10 kHz energy, noise floor, modulation, spectral roughness and Doppler/F0 stability.
- Expert classification for `ЛТ`, `GR2`, `FP-1 (тяж. поршневой)`,
  with `UNKNOWN` below confidence `0.45`.
- Local labeled sound dataset and KNN/prototype classifier for separating custom
  classes such as UAV types, wind, cars, generators and aircraft.
- Acoustic passport with human-readable explanation.
- Multi-microphone localization using GCC-PHAT and least-squares TDOA.
- 2D and 3D microphone configurations.
- Windowed tracking with 0.5 second windows.
- Placeholder architecture for a future Kalman Filter.
- Offline web interface with local Bootstrap-compatible styling and embedded Plotly HTML.
- JSON, CSV and PNG exports.
- Logging to `output/dai.log`.
- REST endpoints for future service integration.

## Project Structure

```text
drone_acoustic_intelligence/
  app.py
  config.py
  requirements.txt
  README.md
  audio/
    analyzer.py
    features.py
    loader.py
    preprocessing.py
  classification/
    expert_system.py
    profiles.py
  ml/
    cluster_classifier.py
    dataset.py
    feature_vector.py
  localization/
    gcc_phat.py
    geometry.py
    localizer.py
  tracking/
    tracker.py
  visualization/
    plots.py
  utils/
    file_utils.py
    logging_utils.py
    serialization.py
    validation.py
  models/
    audio_cluster_model.json
    schemas.py
  dataset/
    features.csv
    raw/
  templates/
  static/
  uploads/
  output/
  tests/
```

## Installation

Python 3.12 is recommended.

```bash
cd drone_acoustic_intelligence
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Run

```bash
cd drone_acoustic_intelligence
source .venv/bin/activate
uvicorn app:app --host 127.0.0.1 --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

Everything is designed to work offline after dependencies are installed. Generated reports are written to `output/<uuid>/`, uploads are stored in `uploads/<uuid>/`.

## Web Interface

The main page contains two workflows:

- `Анализ одного файла`
- `Локализация по нескольким микрофонам`

### Single Audio Analysis

Upload one `.wav` or `.mp3` file and click `Анализировать`.

The result page shows:

- UAV type.
- Confidence.
- Fundamental frequency.
- Harmonic count.
- Harmonic step.
- Stability.
- Spectrogram.
- FFT.
- Harmonic plot.
- Fundamental-frequency track.
- Text explanation.
- Acoustic passport.
- `report.json` download.

### Localization

Upload several `.wav` or `.mp3` files and one `mics.json`, then click `Локализовать`.

The result page shows:

- Microphone map.
- Estimated coordinates.
- TDOA table.
- Trajectory.
- Average speed.
- Course per track point.
- Interactive offline Plotly graph.
- `report.json`, `track.json`, `track.csv`, `track.png`.

## mics.json Format

```json
{
  "speed_of_sound": 343,
  "temperature": 20,
  "coordinate_system": "local_xy",
  "microphones": [
    {
      "id": "mic1",
      "x": 0,
      "y": 0,
      "z": 2,
      "file": "mic1.wav"
    },
    {
      "id": "mic2",
      "x": 50,
      "y": 0,
      "z": 2,
      "file": "mic2.wav"
    },
    {
      "id": "mic3",
      "x": 0,
      "y": 50,
      "z": 2,
      "file": "mic3.wav"
    },
    {
      "id": "mic4",
      "x": 50,
      "y": 50,
      "z": 2,
      "file": "mic4.wav"
    }
  ]
}
```

Use `coordinate_system: "local_xy"` for 2D and `"local_xyz"` for 3D. Fewer than four microphones are accepted, but the application warns that accuracy is limited. For robust 2D localization, use at least three microphones. For robust 3D localization, use at least four.

## Algorithms

### Audio Preprocessing

Each uploaded WAV/MP3 is loaded, converted to mono, DC-corrected and peak-normalized. WAV is read through SoundFile; MP3 uses SoundFile when available and falls back to Librosa/audioread. If sample rate is below 20 kHz, the report includes a warning because high-frequency 6-10 kHz features become less reliable. MP3 reports also include a warning that compression can reduce spectral and TDOA precision.

### Feature Extraction

The DSP pipeline builds:

- FFT.
- STFT spectrogram.
- Mel spectrogram.
- Waveform time axis.
- Fundamental frequency track with `librosa.yin`.
- Harmonic peaks from the FFT.
- RMS and average energy.
- Zero crossing rate.
- Spectral centroid, flatness and bandwidth.
- MFCC mean and standard deviation.
- Noise floor and 6-10 kHz band energy.
- Fundamental variation and harmonic variation.
- Frequency modulation index.
- Spectral roughness.
- Doppler/F0 stability.

### Acoustic Profiles

`ЛТ`:

- Base frequency: 70-120 Hz.
- 20-30 harmonics.
- Very stable.
- Smooth hum.
- Hiss in 6-10 kHz.

`GR2`:

- Base frequency: 80-150 Hz.
- 10-15 harmonics.
- Uneven harmonics.
- Rattling sound.
- No strong hiss.

`FP-1 (тяж. поршневой)`:

- Base frequency: 100-180 Hz.
- Metallic ringing.
- Strong frequency modulation.
- Blurred peaks with side lobes from RPM instability.
- Low stability.
- Pop/crackle texture from propeller and exhaust interaction.
- Harmonic count and 6-10 kHz hiss are not scored for FP-1 until those
  table rows are supplied explicitly.

### Expert Classifier

The expert system assigns each profile a score from `0` to `1` using weighted rules. The best profile is returned as `best_match`. If confidence is below `0.45`, the result is `UNKNOWN`.

New profiles can be added in `classification/profiles.py`, and scoring logic can be extended in `classification/expert_system.py`.

### Local Sound Dataset and ML Classifier

The `/dataset` page adds a second classification layer that is learned from
local labeled recordings. It does not replace the expert system. It stores
windowed DSP features and trains a compact standardized KNN/prototype model.

Runtime files:

- `dataset/raw/<label>/...` stores uploaded labeled audio.
- `dataset/features.csv` stores one row per audio window.
- `models/audio_cluster_model.json` stores the trained local model.

Recommended starter labels:

- `FP-1`
- `GR2`
- `ЛТ`
- `ветер`
- `машины`
- `генератор`
- `самолет`
- `вертолет`
- `городской шум`
- `UNKNOWN`

Workflow:

1. Open `http://127.0.0.1:8001/dataset`.
2. Enter the class label.
3. Upload one or more WAV/MP3 files for that class.
4. Keep the default `1.0 s` window and `0.5 s` hop for the first dataset.
5. Repeat for at least two classes.
6. Click `Обучить модель`.
7. Run a normal single-file analysis. If the model exists, the result page
   also shows `Локальная модель` with class, confidence and competing clusters.

The first ML model is intentionally simple and transparent. It standardizes
feature vectors, stores real labeled audio-window prototypes, keeps centroid
metadata for each label, and classifies new audio by nearest-neighbor voting
over windows. This is useful for gradually building a real dataset before
replacing the backend with RandomForest, XGBoost, SVM or CNN.

### Localization

The localization pipeline:

1. Loads WAV/MP3 files listed in `mics.json`.
2. Resamples all microphone signals to the first file's sample rate if needed.
3. Uses the first microphone as the TDOA reference.
4. Estimates delay with GCC-PHAT for every microphone pair against the reference.
5. Converts delay to distance delta with the configured speed of sound.
6. Solves source position with SciPy least squares.
7. Computes residual RMSE and confidence.

### Tracking

The tracker splits synchronized audio into 0.5 second windows. For each window it estimates position, speed, course and confidence. `tracking/tracker.py` contains a no-op `KalmanFilterHook`, so a Kalman filter can be inserted later without changing the localization service or web routes.

## REST API

Single-file analysis:

```bash
curl -F "wav_file=@sample.mp3" http://127.0.0.1:8000/api/analyze-single
```

Localization:

```bash
curl \
  -F "wav_files=@mic1.wav" \
  -F "wav_files=@mic2.mp3" \
  -F "wav_files=@mic3.wav" \
  -F "mics_json=@mics.json" \
  http://127.0.0.1:8000/api/localize
```

## Tests

```bash
cd drone_acoustic_intelligence
pytest
```

The included tests cover the expert classifier, local cluster classifier,
GCC-PHAT delay estimation and basic feature extraction on synthetic drone-like
tones.

## Extension Points

The architecture is intentionally modular:

- Add neural models by creating a new classifier class behind the same `classify(features)` interface.
- Replace `CentroidAudioClassifier` with RandomForest, XGBoost, SVM or a CNN
  while keeping the dataset page and report schema.
- Add new UAV profiles in `classification/profiles.py`.
- Add streaming microphone capture beside `audio/loader.py`.
- Support large microphone networks by replacing `TdoaGeometrySolver` with a station-aware solver.
- Export reports through more REST routes without changing core algorithms.
- Replace `KalmanFilterHook` with a real filter in `tracking/tracker.py`.

## Notes

The system estimates acoustic source position from uploaded synchronized WAV/MP3 files. Real-world accuracy depends on synchronization quality, microphone geometry, SNR, reverberation, wind, compression artifacts, and correct speed-of-sound settings.
