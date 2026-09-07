"""Matplotlib and Plotly visualizations for DAI reports."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import plotly.graph_objects as go

from audio.features import FeatureExtractionResult
from config import settings
from models.schemas import MicrophoneArrayConfig, SourcePosition, TrackPoint


class PlotGenerator:
    """Create PNG and offline HTML plots for reports."""

    def create_audio_plots(
        self,
        extraction: FeatureExtractionResult,
        output_dir: Path,
    ) -> dict[str, str]:
        """Create all plots for a single-file analysis."""

        output_dir.mkdir(parents=True, exist_ok=True)
        plots = {
            "waveform": output_dir / "waveform.png",
            "fft": output_dir / "fft.png",
            "spectrogram": output_dir / "spectrogram.png",
            "mel_spectrogram": output_dir / "mel_spectrogram.png",
            "harmonics": output_dir / "harmonics.png",
            "energy_heatmap": output_dir / "energy_heatmap.png",
            "fundamental_track": output_dir / "fundamental_track.png",
        }

        self._waveform(extraction, plots["waveform"])
        self._fft(extraction, plots["fft"])
        self._spectrogram(extraction, plots["spectrogram"])
        self._mel(extraction, plots["mel_spectrogram"])
        self._harmonics(extraction, plots["harmonics"])
        self._energy_heatmap(extraction, plots["energy_heatmap"])
        self._fundamental_track(extraction, plots["fundamental_track"])
        return {name: str(path) for name, path in plots.items()}

    def create_localization_plots(
        self,
        config: MicrophoneArrayConfig,
        position: SourcePosition,
        track: list[TrackPoint],
        output_dir: Path,
    ) -> dict[str, str]:
        """Create localization map, trajectory image and offline Plotly figure."""

        output_dir.mkdir(parents=True, exist_ok=True)
        mic_map = output_dir / "microphone_map.png"
        track_png = output_dir / "track.png"
        track_html = output_dir / "trajectory_plot.html"

        self._microphone_map(config, position, track, mic_map)
        self._trajectory_png(config, track, track_png)
        self._trajectory_plotly(config, position, track, track_html)

        return {
            "microphone_map": str(mic_map),
            "track": str(track_png),
            "trajectory_html": str(track_html),
        }

    @staticmethod
    def _style_axes(ax: plt.Axes, title: str, xlabel: str, ylabel: str) -> None:
        """Apply consistent plot styling."""

        ax.set_title(title)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.grid(True, alpha=0.25)

    @staticmethod
    def _save(fig: plt.Figure, path: Path) -> None:
        """Save a Matplotlib figure and close it."""

        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)

    def _waveform(self, extraction: FeatureExtractionResult, path: Path) -> None:
        """Plot waveform."""

        time, waveform = self._decimate(extraction.waveform_time, extraction.waveform)
        fig, ax = plt.subplots(figsize=(11, 4))
        ax.plot(time, waveform, linewidth=0.7, color="#1f6feb")
        self._style_axes(ax, "Waveform", "Time, s", "Amplitude")
        self._save(fig, path)

    def _fft(self, extraction: FeatureExtractionResult, path: Path) -> None:
        """Plot FFT magnitude."""

        max_freq = min(settings.fft_max_frequency_hz, float(np.max(extraction.fft_frequency)))
        mask = extraction.fft_frequency <= max_freq
        fig, ax = plt.subplots(figsize=(11, 4))
        ax.plot(
            extraction.fft_frequency[mask],
            extraction.fft_magnitude[mask],
            linewidth=0.8,
            color="#b42318",
        )
        self._style_axes(ax, "FFT Spectrum", "Frequency, Hz", "Normalized magnitude")
        self._save(fig, path)

    def _spectrogram(self, extraction: FeatureExtractionResult, path: Path) -> None:
        """Plot STFT spectrogram."""

        max_freq = min(settings.fft_max_frequency_hz, float(np.max(extraction.stft_frequency)))
        freq_mask = extraction.stft_frequency <= max_freq
        fig, ax = plt.subplots(figsize=(11, 5))
        im = ax.imshow(
            extraction.stft_db[freq_mask, :],
            aspect="auto",
            origin="lower",
            cmap="magma",
            extent=[
                float(np.min(extraction.stft_time)) if extraction.stft_time.size else 0.0,
                float(np.max(extraction.stft_time)) if extraction.stft_time.size else 0.0,
                0.0,
                max_freq,
            ],
        )
        self._style_axes(ax, "STFT Spectrogram", "Time, s", "Frequency, Hz")
        fig.colorbar(im, ax=ax, label="dB")
        self._save(fig, path)

    def _mel(self, extraction: FeatureExtractionResult, path: Path) -> None:
        """Plot Mel spectrogram."""

        fig, ax = plt.subplots(figsize=(11, 5))
        im = ax.imshow(
            extraction.mel_db,
            aspect="auto",
            origin="lower",
            cmap="viridis",
            extent=[
                0.0,
                float(np.max(extraction.stft_time)) if extraction.stft_time.size else 0.0,
                float(np.min(extraction.mel_frequency)) if extraction.mel_frequency.size else 0.0,
                float(np.max(extraction.mel_frequency)) if extraction.mel_frequency.size else 0.0,
            ],
        )
        self._style_axes(ax, "Mel Spectrogram", "Time, s", "Mel frequency, Hz")
        fig.colorbar(im, ax=ax, label="dB")
        self._save(fig, path)

    def _harmonics(self, extraction: FeatureExtractionResult, path: Path) -> None:
        """Plot harmonic peaks over FFT."""

        features = extraction.features
        max_freq = min(settings.fft_max_frequency_hz, float(np.max(extraction.fft_frequency)))
        mask = extraction.fft_frequency <= max_freq
        fig, ax = plt.subplots(figsize=(11, 4))
        ax.plot(
            extraction.fft_frequency[mask],
            extraction.fft_magnitude[mask],
            linewidth=0.7,
            color="#475467",
        )
        if features.detected_harmonics_hz:
            harmonic_freqs = np.array(features.detected_harmonics_hz)
            harmonic_mags = np.interp(
                harmonic_freqs,
                extraction.fft_frequency,
                extraction.fft_magnitude,
            )
            ax.scatter(harmonic_freqs, harmonic_mags, color="#079455", s=28, zorder=3)
        self._style_axes(ax, "Detected Harmonics", "Frequency, Hz", "Normalized magnitude")
        self._save(fig, path)

    def _energy_heatmap(self, extraction: FeatureExtractionResult, path: Path) -> None:
        """Plot STFT energy heatmap."""

        max_freq = min(settings.fft_max_frequency_hz, float(np.max(extraction.stft_frequency)))
        freq_mask = extraction.stft_frequency <= max_freq
        energy = np.maximum(extraction.stft_db[freq_mask, :], -80.0)
        fig, ax = plt.subplots(figsize=(11, 5))
        im = ax.imshow(
            energy,
            aspect="auto",
            origin="lower",
            cmap="inferno",
            extent=[
                float(np.min(extraction.stft_time)) if extraction.stft_time.size else 0.0,
                float(np.max(extraction.stft_time)) if extraction.stft_time.size else 0.0,
                0.0,
                max_freq,
            ],
        )
        self._style_axes(ax, "Energy Heatmap", "Time, s", "Frequency, Hz")
        fig.colorbar(im, ax=ax, label="dB")
        self._save(fig, path)

    def _fundamental_track(self, extraction: FeatureExtractionResult, path: Path) -> None:
        """Plot F0 track."""

        features = extraction.features
        fig, ax = plt.subplots(figsize=(11, 4))
        if features.f0_track_hz and features.time_axis_seconds:
            ax.plot(
                features.time_axis_seconds,
                features.f0_track_hz,
                linewidth=1.2,
                color="#7a271a",
            )
        else:
            ax.text(
                0.5,
                0.5,
                "No stable F0 track detected",
                ha="center",
                va="center",
                transform=ax.transAxes,
            )
        self._style_axes(ax, "Fundamental Frequency Track", "Time, s", "F0, Hz")
        self._save(fig, path)

    def _microphone_map(
        self,
        config: MicrophoneArrayConfig,
        position: SourcePosition,
        track: list[TrackPoint],
        path: Path,
    ) -> None:
        """Plot microphone positions and estimated source."""

        fig, ax = plt.subplots(figsize=(8, 7))
        xs = [mic.x for mic in config.microphones]
        ys = [mic.y for mic in config.microphones]
        ax.scatter(xs, ys, marker="^", s=90, color="#1f6feb", label="Microphones")
        for mic in config.microphones:
            ax.annotate(mic.id, (mic.x, mic.y), textcoords="offset points", xytext=(6, 6))
        ax.scatter([position.x], [position.y], marker="*", s=180, color="#b42318", label="Source")
        if track:
            ax.plot(
                [point.x for point in track],
                [point.y for point in track],
                color="#079455",
                linewidth=1.5,
                label="Track",
            )
        ax.axis("equal")
        ax.legend(loc="best")
        self._style_axes(ax, "Microphone Map", "X, m", "Y, m")
        self._save(fig, path)

    def _trajectory_png(
        self,
        config: MicrophoneArrayConfig,
        track: list[TrackPoint],
        path: Path,
    ) -> None:
        """Plot trajectory with confidence coloring."""

        fig, ax = plt.subplots(figsize=(9, 6))
        ax.scatter(
            [mic.x for mic in config.microphones],
            [mic.y for mic in config.microphones],
            marker="^",
            s=80,
            color="#475467",
            label="Microphones",
        )
        if track:
            x = np.array([point.x for point in track])
            y = np.array([point.y for point in track])
            confidence = np.array([point.confidence for point in track])
            ax.plot(x, y, linewidth=1.0, color="#344054", alpha=0.6)
            scatter = ax.scatter(x, y, c=confidence, cmap="plasma", s=42, vmin=0, vmax=1)
            fig.colorbar(scatter, ax=ax, label="Confidence")
        ax.axis("equal")
        ax.legend(loc="best")
        self._style_axes(ax, "Trajectory", "X, m", "Y, m")
        self._save(fig, path)

    @staticmethod
    def _trajectory_plotly(
        config: MicrophoneArrayConfig,
        position: SourcePosition,
        track: list[TrackPoint],
        path: Path,
    ) -> None:
        """Create an offline interactive Plotly trajectory HTML."""

        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=[mic.x for mic in config.microphones],
                y=[mic.y for mic in config.microphones],
                mode="markers+text",
                text=[mic.id for mic in config.microphones],
                textposition="top center",
                marker=dict(symbol="triangle-up", size=14, color="#1f6feb"),
                name="Microphones",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=[position.x],
                y=[position.y],
                mode="markers",
                marker=dict(symbol="star", size=18, color="#b42318"),
                name="Estimated source",
            )
        )
        if track:
            fig.add_trace(
                go.Scatter(
                    x=[point.x for point in track],
                    y=[point.y for point in track],
                    mode="lines+markers",
                    marker=dict(
                        size=8,
                        color=[point.confidence for point in track],
                        colorscale="Plasma",
                        cmin=0,
                        cmax=1,
                        showscale=True,
                        colorbar=dict(title="Confidence"),
                    ),
                    text=[
                        f"t={point.time_seconds:.2f}s<br>"
                        f"speed={point.speed_mps if point.speed_mps is not None else 0:.2f} m/s"
                        for point in track
                    ],
                    name="Track",
                )
            )
        fig.update_layout(
            title="Localization and Track",
            xaxis_title="X, m",
            yaxis_title="Y, m",
            yaxis_scaleanchor="x",
            template="plotly_white",
            margin=dict(l=40, r=20, t=60, b=40),
        )
        path.write_text(fig.to_html(include_plotlyjs=True, full_html=True), encoding="utf-8")

    @staticmethod
    def _decimate(x: np.ndarray, y: np.ndarray, max_points: int = 20_000) -> tuple[np.ndarray, np.ndarray]:
        """Downsample arrays for plotting without changing the source data."""

        if len(x) <= max_points:
            return x, y
        step = int(np.ceil(len(x) / max_points))
        return x[::step], y[::step]

