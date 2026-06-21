"""Statistical drift detectors and the multi-stream fusion gateway."""

from __future__ import annotations

from .fusion import DriftFusion, FusionResult, StreamSignal
from .page_hinkley import PageHinkleyDetector, cosine_distance
from .transaction import QuantitativeTransactionStream

__all__ = [
    "PageHinkleyDetector",
    "cosine_distance",
    "QuantitativeTransactionStream",
    "DriftFusion",
    "FusionResult",
    "StreamSignal",
]
