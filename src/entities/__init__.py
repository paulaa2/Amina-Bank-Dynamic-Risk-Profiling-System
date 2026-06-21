"""Deterministic entity resolution against a closed graph of known nodes."""

from __future__ import annotations

from .resolver import EntityRegistry, EntityResolver, normalize_name

__all__ = ["EntityRegistry", "EntityResolver", "normalize_name"]
