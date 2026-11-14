"""AudioLoader: analysis-rate resampling (station rate 32 kHz)."""


def test_loader_resamples_to_the_station_rate(tmp_path):
    """Every analysis runs at the station's 32 kHz (settings.target_analysis_sample_rate_hz): a 48 kHz file is
    resampled on load and the loaded sample_rate reports 32000, so features match the firmware extractor."""
    import numpy as np
    import soundfile as sf
    from audio.loader import AudioLoader
    from config import settings
    assert settings.target_analysis_sample_rate_hz == 32000
    sr = 48000
    t = np.arange(sr * 2) / sr
    y = (0.5 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    path = tmp_path / "tone48k.wav"
    sf.write(path, y, sr)
    loaded = AudioLoader().load_audio(path)
    assert loaded.sample_rate == 32000
    assert abs(loaded.duration_seconds - 2.0) < 0.01
    assert any("resampled to the analysis rate 32000" in w for w in loaded.warnings)
    spectrum = np.abs(np.fft.rfft(loaded.signal[:32000]))
    peak_hz = float(np.argmax(spectrum))            # 1 s window: bin = Hz
    assert abs(peak_hz - 440.0) <= 1.0
