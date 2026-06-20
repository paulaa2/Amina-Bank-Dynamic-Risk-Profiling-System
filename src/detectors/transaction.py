"""Quantitative transactional drift stream.

Monitors the behavioural dimension of KYC drift: how far a new transaction
deviates from the client's recent moving average, expressed as an absolute
Z-score over a sliding window. A short warm-up phase returns zero until enough
history has accumulated to estimate a stable mean and variance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class QuantitativeTransactionStream:
    """Sliding-window absolute Z-score detector for transaction amounts."""

    window_size: int = 30
    warmup: int = 5
    history: list[float] = field(default_factory=list)

    def record_transaction(self, amount: float) -> float:
        """Record a transfer and return its absolute Z-score against the window."""
        if len(self.history) < self.warmup:
            self.history.append(amount)
            return 0.0

        window = self.history[-self.window_size:]
        mean = sum(window) / len(window)
        var = sum((x - mean) ** 2 for x in window) / len(window)
        std = math.sqrt(var) if var > 0 else 1.0

        z_score = abs(amount - mean) / std
        self.history.append(amount)
        return float(z_score)

    def seed_history(self, amounts: list[float]) -> None:
        """Pre-load historic amounts without emitting Z-scores."""
        self.history.extend(amounts)
