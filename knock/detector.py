"""Public engine joining calibration, training, streaming closure, and matching."""

from __future__ import annotations

import time

import numpy as np

from .audio import TARGET_SAMPLE_RATE, resample, robust_noise_rms
from .features import FeatureError, extract_signature, onset_indices
from .learner import MotifLearner


class KnockEngine:
    """Learn one short acoustic motif, then recognize it in a live PCM stream."""

    def __init__(self, sample_rate: int) -> None:
        self.sample_rate = int(sample_rate)
        if self.sample_rate <= 0:
            raise ValueError("sample_rate must be positive")
        self.learner = MotifLearner()
        self.noise_rms = 1e-4
        self._stream = np.zeros(0, dtype=np.float32)
        self._total_samples = 0
        self._last_scan = 0
        self._last_candidate_end = -1

    @property
    def ready(self) -> bool:
        return self.learner.ready

    def _target_audio(self, audio) -> np.ndarray:
        return resample(audio, self.sample_rate, TARGET_SAMPLE_RATE)

    def _clear_stream(self) -> None:
        self._stream = np.zeros(0, dtype=np.float32)
        self._total_samples = 0
        self._last_scan = 0
        self._last_candidate_end = -1

    def set_noise(self, audio) -> dict:
        values = self._target_audio(audio)
        self.noise_rms = robust_noise_rms(values, TARGET_SAMPLE_RATE)
        self._clear_stream()
        return {"noise_rms": self.noise_rms}

    def add_example(self, audio) -> dict:
        try:
            signature = extract_signature(
                self._target_audio(audio),
                self.noise_rms,
                TARGET_SAMPLE_RATE,
            )
        except FeatureError as error:
            return {
                "ok": False,
                "reason": str(error),
                "onset_count": 0,
                "example_count": len(self.learner.examples),
                "ready": self.ready,
                "consistency": self.learner.consistency,
            }
        result = self.learner.add(signature)
        result.setdefault("onset_count", signature.onset_count)
        result.setdefault("example_count", len(self.learner.examples))
        result.setdefault("ready", self.ready)
        result.setdefault("consistency", self.learner.consistency)
        if self.ready:
            self._clear_stream()
        return result

    def process(self, audio_chunk) -> dict | None:
        if not self.ready:
            return None

        chunk = self._target_audio(audio_chunk)
        if chunk.size == 0:
            return None
        self._total_samples += chunk.size
        self._stream = np.concatenate((self._stream, chunk))
        max_samples = int(TARGET_SAMPLE_RATE * 4.2)
        if self._stream.size > max_samples:
            self._stream = self._stream[-max_samples:]

        scan_interval = int(TARGET_SAMPLE_RATE * 0.12)
        if self._total_samples - self._last_scan < scan_interval:
            return None
        self._last_scan = self._total_samples

        indices = onset_indices(self._stream, self.noise_rms, TARGET_SAMPLE_RATE)
        if indices.size < 2:
            return None
        silence_after = (self._stream.size - int(indices[-1])) / TARGET_SAMPLE_RATE
        if silence_after < 0.48:
            return None

        gaps = np.diff(indices) / TARGET_SAMPLE_RATE
        split_points = np.flatnonzero(gaps > 0.82)
        start_index = int(split_points[-1] + 1) if split_points.size else 0
        motif_indices = indices[start_index:]
        if motif_indices.size < 2:
            return None

        absolute_last = self._total_samples - self._stream.size + int(motif_indices[-1])
        if absolute_last <= self._last_candidate_end + int(TARGET_SAMPLE_RATE * 0.10):
            return None
        self._last_candidate_end = absolute_last

        started = time.perf_counter()
        begin = max(0, int(motif_indices[0]) - int(TARGET_SAMPLE_RATE * 0.10))
        finish = min(self._stream.size, int(motif_indices[-1]) + int(TARGET_SAMPLE_RATE * 0.22))
        candidate = self._stream[begin:finish]
        try:
            signature = extract_signature(candidate, self.noise_rms, TARGET_SAMPLE_RATE)
            result = self.learner.compare(signature)
            result["onset_count"] = signature.onset_count
            result["reason"] = "matched learned profile" if result["detected"] else "outside learned threshold"
        except FeatureError as error:
            result = {
                "detected": False,
                "confidence": 0.0,
                "distance": 1.0,
                "threshold": self.learner.threshold,
                "onset_count": int(motif_indices.size),
                "reason": str(error),
            }
        result["latency_ms"] = (time.perf_counter() - started) * 1000.0
        return result

    def reset(self) -> None:
        self.learner.reset()
        self.noise_rms = 1e-4
        self._clear_stream()

    def export_profile(self) -> dict:
        profile = self.learner.export_profile()
        profile["threshold"] = self.learner.threshold
        return profile

    def load_profile(self, payload: dict) -> None:
        self.learner.load_profile(payload)
        self._clear_stream()
