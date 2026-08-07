"""Small audio primitives shared by training and streaming inference."""

from __future__ import annotations

import numpy as np


TARGET_SAMPLE_RATE = 16_000


def mono_float(audio) -> np.ndarray:
    """Return finite, centered mono float32 PCM without changing amplitude."""

    values = np.asarray(audio, dtype=np.float32).reshape(-1)
    if values.size == 0:
        return values
    values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    return values - np.float32(np.mean(values))


def resample(audio, source_rate: int, target_rate: int = TARGET_SAMPLE_RATE) -> np.ndarray:
    """Linearly resample a short PCM block."""

    values = mono_float(audio)
    source_rate = int(source_rate)
    target_rate = int(target_rate)
    if values.size < 2 or source_rate == target_rate:
        return values.copy()
    if source_rate <= 0 or target_rate <= 0:
        raise ValueError("sample rates must be positive")

    output_size = max(1, int(round(values.size * target_rate / source_rate)))
    source_positions = np.linspace(0.0, values.size - 1, values.size, dtype=np.float64)
    target_positions = np.linspace(0.0, values.size - 1, output_size, dtype=np.float64)
    return np.interp(target_positions, source_positions, values).astype(np.float32)


def rms(audio) -> float:
    values = mono_float(audio)
    if values.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(values, dtype=np.float64))))


def robust_noise_rms(audio, sample_rate: int = TARGET_SAMPLE_RATE) -> float:
    """Estimate a conservative noise floor from short non-overlapping blocks."""

    values = mono_float(audio)
    block = max(1, int(sample_rate * 0.04))
    usable = values.size - values.size % block
    if usable < block:
        return max(rms(values), 1e-5)
    frames = values[:usable].reshape(-1, block)
    levels = np.sqrt(np.mean(np.square(frames, dtype=np.float64), axis=1))
    return max(float(np.quantile(levels, 0.75)), 1e-5)


def framed_rms(audio, sample_rate: int = TARGET_SAMPLE_RATE) -> tuple[np.ndarray, int]:
    """Return a 20 ms RMS envelope sampled every 10 ms."""

    values = mono_float(audio)
    frame = max(8, int(sample_rate * 0.020))
    hop = max(4, int(sample_rate * 0.010))
    if values.size < frame:
        return np.zeros(0, dtype=np.float32), hop

    power = np.square(values, dtype=np.float64)
    cumulative = np.concatenate(([0.0], np.cumsum(power)))
    starts = np.arange(0, values.size - frame + 1, hop, dtype=np.int64)
    means = (cumulative[starts + frame] - cumulative[starts]) / frame
    return np.sqrt(np.maximum(means, 0.0)).astype(np.float32), hop
