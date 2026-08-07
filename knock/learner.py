"""Three-example prototype learning with calibrated unknown rejection."""

from __future__ import annotations

from itertools import combinations

import numpy as np

from .features import MotifSignature


PROFILE_VERSION = 1


def _dtw(left, right) -> float:
    a = np.asarray(left, dtype=np.float64)
    b = np.asarray(right, dtype=np.float64)
    if a.size == 0 and b.size == 0:
        return 0.0
    if a.size == 0 or b.size == 0:
        return 1.0

    table = np.full((a.size + 1, b.size + 1), np.inf, dtype=np.float64)
    table[0, 0] = 0.0
    for row in range(1, a.size + 1):
        for column in range(1, b.size + 1):
            cost = abs(a[row - 1] - b[column - 1])
            table[row, column] = cost + min(
                table[row - 1, column],
                table[row, column - 1],
                table[row - 1, column - 1],
            )
    return float(table[-1, -1] / max(a.size, b.size))


def signature_distance(left: MotifSignature, right: MotifSignature) -> float:
    count_gap = abs(left.onset_count - right.onset_count)
    count_penalty = 0.42 * count_gap
    rhythm = _dtw(left.intervals, right.intervals)
    amplitude = _dtw(left.amplitudes, right.amplitudes)
    spectrum = _dtw(left.centroids, right.centroids)
    return float(count_penalty + 0.68 * rhythm + 0.18 * amplitude + 0.14 * spectrum)


class MotifLearner:
    def __init__(self) -> None:
        self.examples: list[MotifSignature] = []
        self.threshold = 0.0
        self.consistency = 0.0

    @property
    def ready(self) -> bool:
        return len(self.examples) == 3 and self.threshold > 0.0

    def reset(self) -> None:
        self.examples.clear()
        self.threshold = 0.0
        self.consistency = 0.0

    def add(self, signature: MotifSignature) -> dict:
        if self.ready:
            return {"ok": False, "reason": "The profile already has three examples."}

        if self.examples:
            nearest = min(signature_distance(signature, known) for known in self.examples)
            if nearest > 0.72:
                return {
                    "ok": False,
                    "reason": "That recording differs too much from the earlier examples. Repeat the same pattern.",
                }

        self.examples.append(signature)
        if len(self.examples) == 3:
            pairwise = [signature_distance(a, b) for a, b in combinations(self.examples, 2)]
            spread = max(pairwise)
            self.threshold = float(np.clip(spread * 1.7 + 0.10, 0.20, 0.58))
            self.consistency = float(np.clip(1.0 - spread / 0.72, 0.0, 1.0))
        elif len(self.examples) == 2:
            spread = signature_distance(self.examples[0], self.examples[1])
            self.consistency = float(np.clip(1.0 - spread / 0.72, 0.0, 1.0))
        else:
            self.consistency = 1.0

        return {
            "ok": True,
            "reason": "example accepted",
            "example_count": len(self.examples),
            "ready": self.ready,
            "consistency": self.consistency,
            "onset_count": signature.onset_count,
        }

    def compare(self, signature: MotifSignature) -> dict:
        if not self.ready:
            raise RuntimeError("three examples are required before comparison")
        distances = sorted(signature_distance(signature, known) for known in self.examples)
        distance = float(np.mean(distances[:2]))
        detected = distance <= self.threshold
        confidence = float(np.clip(1.0 - distance / max(self.threshold, 1e-6), 0.0, 1.0))
        return {
            "detected": detected,
            "distance": distance,
            "threshold": self.threshold,
            "confidence": confidence,
        }

    def export_profile(self) -> dict:
        return {
            "version": PROFILE_VERSION,
            "threshold": self.threshold,
            "consistency": self.consistency,
            "examples": [example.to_dict() for example in self.examples],
        }

    def load_profile(self, payload: dict) -> None:
        if int(payload.get("version", -1)) != PROFILE_VERSION:
            raise ValueError("unsupported profile version")
        examples = [MotifSignature.from_dict(item) for item in payload.get("examples", [])]
        threshold = float(payload.get("threshold", 0.0))
        if len(examples) != 3 or not 0.0 < threshold <= 1.5:
            raise ValueError("invalid learned profile")
        self.examples = examples
        self.threshold = threshold
        self.consistency = float(payload.get("consistency", 0.0))
