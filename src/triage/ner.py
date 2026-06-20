"""Stage 1: deterministic relevance triage.

This is the cheapest stage of the pipeline. It discards the bulk of incoming
Layer-1 text that does not explicitly mention the monitored client or any of
its known directors / shareholders, so no local or cloud model is ever invoked
for irrelevant noise.

The default matcher is a zero-dependency alias dictionary (exact and fuzzy
token match). spaCy NER is supported transparently when installed, but is not
required: the dictionary matcher is sufficient and fully deterministic, which
is preferable for auditability.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..entities.resolver import normalize_name


@dataclass
class TriageResult:
    """Outcome of triaging a single piece of text."""

    is_relevant: bool
    matched_terms: list[str] = field(default_factory=list)
    reason: str = ""


class RelevanceTriage:
    """Fast keyword / alias matcher for client and graph-node names."""

    def __init__(self, known_aliases: list[str]) -> None:
        # Keep both the raw lowercased alias and its normalised token form so
        # we catch "MicroStrategy Inc." in text mentioning "MicroStrategy".
        self._aliases: list[tuple[str, str]] = []
        for alias in known_aliases:
            if not alias or not alias.strip():
                continue
            raw = alias.strip().lower()
            norm = normalize_name(alias)
            self._aliases.append((raw, norm))

    def is_relevant(self, text: str) -> TriageResult:
        """Return whether ``text`` mentions any known client / node alias."""
        if not text:
            return TriageResult(False, [], "empty_text")

        lowered = text.lower()
        normalised = normalize_name(text)
        matched: list[str] = []

        for raw, norm in self._aliases:
            if raw and raw in lowered:
                matched.append(raw)
            elif norm and len(norm) >= 3 and norm in normalised:
                matched.append(norm)

        matched = sorted(set(matched))
        if matched:
            return TriageResult(True, matched, "alias_match")
        return TriageResult(False, [], "no_known_entity")
