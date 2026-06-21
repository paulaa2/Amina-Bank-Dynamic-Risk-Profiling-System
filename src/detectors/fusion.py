"""Multi-stream drift fusion with Bonferroni correction.

Three independent statistical streams (semantic, topological, transactional)
are combined into a single, continuous risk score for the analyst inbox.

To control the family-wise error rate (FWER) across ``k`` parallel tests, each
detector's alarm threshold is widened by a logarithmic Bonferroni factor::

    lambda_adjusted = lambda_base * (1 + ln(k))

The per-stream exceedance ratios are then fused under an independent-failure
model (probabilistic OR)::

    R_combined = 1 - product(1 - min(1, T_i / lambda_i) * weight_i)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .page_hinkley import PageHinkleyDetector


@dataclass
class StreamSignal:
    """A named statistical stream with its detector and fusion weight."""

    name: str
    detector: PageHinkleyDetector
    weight: float = 1.0


@dataclass
class FusionResult:
    """Outcome of one fusion update."""

    alarms: dict[str, bool]
    combined_risk: float
    statistics: dict[str, float]
    thresholds: dict[str, float]
    ratios: dict[str, float]

    @property
    def any_alarm(self) -> bool:
        return any(self.alarms.values())

    @property
    def triggered_streams(self) -> list[str]:
        return [name for name, fired in self.alarms.items() if fired]


class DriftFusion:
    """Fuses semantic, topological and transactional streams.

    The Bonferroni widening is applied once, at construction, to every
    detector's threshold.
    """

    def __init__(self, streams: list[StreamSignal], target_fwer: float = 0.05) -> None:
        self.streams = streams
        self.target_fwer = target_fwer
        k = len(streams)
        scale = 1.0 + math.log(k) if k > 1 else 1.0
        self.bonferroni_scale = scale
        for s in streams:
            s.detector.threshold *= scale

    def update(self, observations: dict[str, float]) -> FusionResult:
        """Feed one observation per stream and compute the combined risk."""
        alarms: dict[str, bool] = {}
        statistics: dict[str, float] = {}
        thresholds: dict[str, float] = {}
        ratios: dict[str, float] = {}

        combined_survival = 1.0
        for s in self.streams:
            if s.name not in observations:
                continue
            fired = s.detector.update(observations[s.name])
            stat = s.detector.last_statistic
            thr = s.detector.threshold

            alarms[s.name] = fired
            statistics[s.name] = stat
            thresholds[s.name] = thr

            raw_ratio = stat / thr if thr > 0 else 0.0
            ratio = min(max(raw_ratio, 0.0), 1.0) * s.weight
            ratios[s.name] = ratio
            combined_survival *= (1.0 - ratio)

        return FusionResult(
            alarms=alarms,
            combined_risk=1.0 - combined_survival,
            statistics=statistics,
            thresholds=thresholds,
            ratios=ratios,
        )
