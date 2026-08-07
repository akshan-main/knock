"""Explainable rhythm and spectrum features for short percussive motifs."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .audio import TARGET_SAMPLE_RATE, framed_rms, mono_float


class FeatureError(ValueError):
    """Raised when a recording cannot form a usable motif."""


@dataclass(frozen=True)
class MotifSignature:
    onset_count: int
    intervals: tuple[float, ...]
    amplitudes: tuple[float, ...]
    centroids: tuple[float, ...]

    def to_dict(self) -> dict:
        return {
            "onset_count": self.onset_count,
            "intervals": list(self.intervals),
            "amplitudes": list(self.amplitudes),
            "centroids": list(self.centroids),
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "MotifSignature":
        return cls(
            onset_count=int(payload["onset_count"]),
            intervals=tuple(float(value) for value in payload["intervals"]),
            amplitudes=tuple(float(value) for value in payload["amplitudes"]),
            centroids=tuple(float(value) for value in payload["centroids"]),
        )


def onset_indices(
    audio,
    noise_rms: float,
    sample_rate: int = TARGET_SAMPLE_RATE,
) -> np.ndarray:
    """Locate separated transient peaks using an adaptive RMS envelope."""

    values = mono_float(audio)
    envelope, hop = framed_rms(values, sample_rate)
    if envelope.size < 3:
        return np.zeros(0, dtype=np.int64)

    baseline = float(np.median(envelope))
    mad = float(np.median(np.abs(envelope - baseline)))
    peak = float(np.max(envelope))
    threshold = max(
        float(noise_rms) * 2.8,
        baseline + 5.0 * max(mad, 1e-5),
        peak * 0.16,
        7e-4,
    )
    if peak < threshold:
        return np.zeros(0, dtype=np.int64)

    active = np.flatnonzero(envelope >= threshold)
    if active.size == 0:
        return np.zeros(0, dtype=np.int64)

    groups: list[np.ndarray] = []
    start = 0
    for cursor in range(1, active.size):
        if active[cursor] - active[cursor - 1] > 2:
            groups.append(active[start:cursor])
            start = cursor
    groups.append(active[start:])

    peaks = [int(group[np.argmax(envelope[group])]) for group in groups]
    min_gap_frames = max(1, int(0.085 * sample_rate / hop))
    separated: list[int] = []
    for candidate in peaks:
        if not separated or candidate - separated[-1] >= min_gap_frames:
            separated.append(candidate)
        elif envelope[candidate] > envelope[separated[-1]]:
            separated[-1] = candidate
    return np.asarray(separated, dtype=np.int64) * hop


def _spectral_centroid(values: np.ndarray, center: int, sample_rate: int) -> float:
    radius = max(32, int(sample_rate * 0.035))
    start = max(0, center - radius // 3)
    stop = min(values.size, center + radius)
    segment = values[start:stop]
    if segment.size < 16:
        return 0.0
    windowed = segment * np.hanning(segment.size)
    spectrum = np.abs(np.fft.rfft(windowed))
    total = float(np.sum(spectrum))
    if total <= 1e-9:
        return 0.0
    frequencies = np.fft.rfftfreq(segment.size, 1.0 / sample_rate)
    centroid = float(np.sum(spectrum * frequencies) / total)
    return centroid / (sample_rate / 2.0)


def extract_signature(
    audio,
    noise_rms: float,
    sample_rate: int = TARGET_SAMPLE_RATE,
) -> MotifSignature:
    values = mono_float(audio)
    indices = onset_indices(values, noise_rms, sample_rate)
    count = int(indices.size)
    if count < 2:
        raise FeatureError("No clear pattern found. Use at least two separated knocks, claps, or snaps.")
    if count > 6:
        raise FeatureError("Too many hits found. Use one short pattern with two to six clear hits.")

    times = indices.astype(np.float64) / sample_rate
    intervals = np.diff(times)
    interval_scale = max(float(np.mean(intervals)), 1e-4)
    interval_shape = intervals / interval_scale

    radius = max(16, int(sample_rate * 0.025))
    amplitudes = []
    centroids = []
    for index in indices:
        start = max(0, int(index) - radius)
        stop = min(values.size, int(index) + radius)
        amplitudes.append(float(np.sqrt(np.mean(np.square(values[start:stop], dtype=np.float64)))))
        centroids.append(_spectral_centroid(values, int(index), sample_rate))
    amplitude_scale = max(max(amplitudes), 1e-6)
    amplitude_shape = np.asarray(amplitudes, dtype=np.float64) / amplitude_scale

    return MotifSignature(
        onset_count=count,
        intervals=tuple(round(float(value), 6) for value in interval_shape),
        amplitudes=tuple(round(float(value), 6) for value in amplitude_shape),
        centroids=tuple(round(float(value), 6) for value in centroids),
    )
