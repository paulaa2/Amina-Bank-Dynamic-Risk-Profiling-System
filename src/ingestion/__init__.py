"""Read-only access to the risk-profiling database (integration boundary)."""

from __future__ import annotations

from .repository import (
    ClientProfile,
    ClientProfileRepository,
    NewsEvent,
    TopologyEdgeDTO,
    TopologyNodeDTO,
)

__all__ = [
    "ClientProfileRepository",
    "ClientProfile",
    "NewsEvent",
    "TopologyNodeDTO",
    "TopologyEdgeDTO",
]
