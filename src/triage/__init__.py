"""Stage 1 - cheap, local relevance triage (no LLM cost)."""

from __future__ import annotations

from .ner import TriageResult, RelevanceTriage

__all__ = ["RelevanceTriage", "TriageResult"]
