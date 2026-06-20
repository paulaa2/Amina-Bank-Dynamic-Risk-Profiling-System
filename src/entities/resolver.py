"""High-precision entity resolution.

Mentions extracted from public text are mapped onto the closed list of nodes
already present in the compliance graph, to avoid creating duplicate nodes and
to anchor LLM reasoning to known IDs.

Design guardrail: the fuzzy scorer is restricted to ``rapidfuzz.fuzz.ratio``.
``WRatio`` is explicitly forbidden because it scores "Wirecard" against
"Wirecard Asia Pacific Pte Ltd" at ~90 via substring containment, which would
silently merge an offshore subsidiary into its parent and destroy the
separation needed to detect layering.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

_LEGAL_SUFFIXES = re.compile(
    r"\b(GmbH|AG|Ltd\.?|Inc\.?|LLC|PLC|S\.?A\.?|SE|SRL|SpA|BV|NV|Co\.?|"
    r"Corp\.?|Corporation|Incorporated|Limited|Holdings?|Group|PJSC|JSC|OAO)\b",
    re.IGNORECASE,
)

_STRICT_SUB_ENTITY_TERMS = {
    "georgia",
    "europe",
    "uk",
    "london",
    "asia",
    "pacific",
    "swiss",
    "switzerland",
    "zurich",
    "singapore",
    "hong kong",
    "usa",
    "limited",
    "subsidiary",
    "branch",
}


def normalize_name(name: str) -> str:
    """Strip legal suffixes and punctuation, lowercase and collapse spaces."""
    if not name:
        return ""
    stripped = _LEGAL_SUFFIXES.sub("", name)
    stripped = stripped.replace(".", " ")
    stripped = re.sub(r"\s+", " ", stripped)
    return stripped.strip().lower()


def strict_entity_pre_check(mention: str, canonical_name: str) -> bool:
    """Block automatic parent/subsidiary fusion on explicit local qualifiers.

    A mention such as "VTB Bank Georgia" must not resolve to "VTB Bank" just
    because the shared parent name has a high fuzzy score. If the mention
    carries a geographic or structural qualifier absent from the canonical
    anchor, force the entity to be treated as new.
    """
    mention_lower = mention.lower()
    canonical_lower = canonical_name.lower()
    for term in _STRICT_SUB_ENTITY_TERMS:
        if term in mention_lower and term not in canonical_lower:
            return False
    return True


@dataclass
class EntityRegistry:
    """Closed list of canonical graph nodes keyed by stable node ID."""

    canonical: dict[str, dict] = field(default_factory=dict)

    def add_entity(
        self, node_id: str, aliases: list[str], entity_type: str = "company"
    ) -> None:
        """Register a node and its normalised aliases."""
        normalised = [normalize_name(a) for a in aliases if a and a.strip()]
        self.canonical[node_id] = {
            "aliases": normalised,
            "display_name": aliases[0] if aliases else node_id,
            "type": entity_type,
        }

    def __len__(self) -> int:
        return len(self.canonical)


class EntityResolver:
    """Resolves a free-text mention to a known node ID via ``fuzz.ratio``."""

    def __init__(self, registry: EntityRegistry, fuzzy_high: float = 90.0) -> None:
        self.registry = registry
        self.fuzzy_high = fuzzy_high

    def resolve(self, mention: str) -> dict:
        """Return the matched node ID (and method) or flag a new entity.

        A score at or above ``fuzzy_high`` resolves deterministically. Below
        that, the mention is treated as ambiguous (``needs_llm``) so a closed-
        list LLM pass can decide, rather than guessing here.
        """
        aliases: list[str] = []
        node_ids: list[str] = []
        canonical_names: list[str] = []
        for nid, data in self.registry.canonical.items():
            for alias in data["aliases"]:
                aliases.append(alias)
                node_ids.append(nid)
                canonical_names.append(str(data.get("display_name") or alias))

        if not aliases:
            return {"node_id": None, "is_new": True, "method": "empty_registry", "score": 0.0}

        target = normalize_name(mention)
        if not target:
            return {"node_id": None, "is_new": True, "method": "blank_mention", "score": 0.0}

        result = process.extractOne(target, aliases, scorer=fuzz.ratio)
        if result is None:
            return {"node_id": None, "is_new": True, "method": "no_match", "score": 0.0}

        matched_alias, score, index = result
        if score >= self.fuzzy_high:
            if not strict_entity_pre_check(mention, canonical_names[index]):
                return {
                    "node_id": None,
                    "is_new": True,
                    "method": "strict_sub_entity_guardrail",
                    "score": float(score),
                    "blocked_alias": matched_alias,
                    "blocked_node_id": node_ids[index],
                }
            return {
                "node_id": node_ids[index],
                "is_new": False,
                "method": "fuzzy_ratio",
                "score": float(score),
            }
        return {
            "node_id": None,
            "is_new": True,
            "method": "needs_llm",
            "score": float(score),
        }
