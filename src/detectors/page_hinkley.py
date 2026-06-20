"""Page-Hinkley concept-drift detector with synthetic burn-in calibration.

The Page-Hinkley test is a sequential change-point detector. For a stream of
observations ``x_t`` it tracks a running mean and a cumulative deviation
(CUSUM); an alarm fires when the gap between the running CUSUM and its historic
minimum exceeds an alarm threshold ``lambda``.

This implementation is calibrated from the client's onboarding profile: a small
synthetic baseline of "normal" observations sets the tolerance ``delta`` and the
alarm threshold from the empirical standard deviation, and pre-loads the
observation counter so the very first real event cannot dominate the mean
(the cold-start / burn-in problem).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np


def cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine distance ``1 - cos(a, b)`` with division-by-zero protection."""
    a_arr = np.asarray(a, dtype=float)
    b_arr = np.asarray(b, dtype=float)
    denom = float(np.linalg.norm(a_arr) * np.linalg.norm(b_arr)) + 1e-9
    return float(1.0 - (a_arr @ b_arr) / denom)


@dataclass
class PageHinkleyDetector:
    """Sequential Page-Hinkley detector.

    Must be calibrated with :meth:`seed` before any call to :meth:`update`.
    """

    delta: float = 0.0
    threshold: float = 0.0
    last_statistic: float = 0.0

    _mean: float = field(default=0.0, repr=False)
    _n: int = field(default=0, repr=False)
    _cum_sum: float = field(default=0.0, repr=False)
    _min_cum_sum: float = field(default=0.0, repr=False)
    _seeded: bool = field(default=False, repr=False)

    def seed(
        self,
        baseline_values: Sequence[float],
        k_std_delta: float = 3.0,
        k_std_threshold: float = 6.0,
    ) -> None:
        """Calibrate ``delta`` and ``threshold`` from baseline observations.

        ``k_std_delta`` and ``k_std_threshold`` express the tolerance and the
        alarm threshold as multiples of the baseline standard deviation. The
        observation counter ``n`` is locked to the baseline size so the running
        mean is well damped against the first real observation.
        """
        if len(baseline_values) < 3:
            raise ValueError(
                "Detector calibration requires at least 3 baseline observations."
            )
        n = len(baseline_values)
        mean = sum(baseline_values) / n
        var = sum((x - mean) ** 2 for x in baseline_values) / max(n - 1, 1)
        std = math.sqrt(var) if var > 0 else 1e-3

        self._mean = mean
        self._n = n  # damping prior for the running mean
        self.delta = k_std_delta * std
        self.threshold = k_std_threshold * std
        self._cum_sum = 0.0
        self._min_cum_sum = 0.0
        self.last_statistic = 0.0
        self._seeded = True

    def update(self, x: float) -> bool:
        """Feed one observation and return whether the alarm condition holds."""
        if not self._seeded:
            raise RuntimeError(
                "Operation rejected: the detector has not been calibrated via seed()."
            )
        self._n += 1
        self._mean += (x - self._mean) / self._n
        self._cum_sum += x - self._mean - self.delta
        self._min_cum_sum = min(self._min_cum_sum, self._cum_sum)
        self.last_statistic = self._cum_sum - self._min_cum_sum
        return self.last_statistic > self.threshold

    @property
    def is_seeded(self) -> bool:
        return self._seeded


def generate_synthetic_baseline(
    company_profile: str,
    m0: Sequence[float],
    embed_fn: Callable[[str], Sequence[float]],
    headline_fn: Callable[[str, int], Sequence[str]],
    k: int = 20,
) -> list[float]:
    """Build a cold-start baseline of cosine distances for calibration.

    ``headline_fn`` returns ``k`` routine, in-profile headlines for the company;
    ``embed_fn`` maps text to a vector. The returned distances describe the
    "normal" semantic spread of the client and are passed to
    :meth:`PageHinkleyDetector.seed`.
    """
    headlines = list(headline_fn(company_profile, k))
    distances: list[float] = []
    for text in headlines:
        try:
            distances.append(cosine_distance(embed_fn(text), m0))
        except Exception:
            continue
    return distances
