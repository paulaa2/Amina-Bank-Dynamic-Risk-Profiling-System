"""The three specialised compliance agents.

- :class:`SentinelExtractor` (local, Ollama): strips journalistic noise from a
  Layer-1 event and returns an atomic corporate fact for embedding.
- :class:`AMLSynthesizer` (cloud, Groq): drafts the final EDD report from the
  de-anonymised anomaly trace.

Both agents degrade gracefully: a failed local extraction falls back to the raw
(masked) headline so the statistical pipeline can still run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .groq_client import GroqClient
from .ollama_client import OllamaClient
from .prompts import (
    AML_SYNTHESIZER_SYSTEM_PROMPT,
    SENTINEL_SYSTEM_PROMPT,
    SYNTHETIC_HEADLINE_PROMPT,
)


@dataclass
class ExtractedFact:
    """Structured output of the Sentinel agent."""

    target_entity: str
    core_action_description: str
    entities_involved: list[dict]
    used_fallback: bool = False

    @property
    def text_for_embedding(self) -> str:
        """The atomic fact text fed to the embedding model."""
        return self.core_action_description or self.target_entity


class SentinelExtractor:
    """Local fact-extraction agent (Stage 2)."""

    def __init__(self, client: OllamaClient) -> None:
        self.client = client

    def extract(self, masked_text: str) -> ExtractedFact:
        """Extract an atomic corporate fact from masked Layer-1 text."""
        try:
            data = self.client.chat_json(SENTINEL_SYSTEM_PROMPT, masked_text)
            description = (data.get("core_action_description") or "").strip()
            if description:
                return ExtractedFact(
                    target_entity=(data.get("target_entity") or "").strip(),
                    core_action_description=description,
                    entities_involved=data.get("entities_involved") or [],
                )
        except Exception:
            pass
        # Fallback: use the masked headline directly so drift math still runs.
        return ExtractedFact(
            target_entity="",
            core_action_description=masked_text.strip(),
            entities_involved=[],
            used_fallback=True,
        )

    def synthetic_headlines(self, company_profile: str, k: int = 20) -> list[str]:
        """Generate routine in-profile headlines for cold-start calibration."""
        prompt = SYNTHETIC_HEADLINE_PROMPT.format(k=k, profile=company_profile)
        try:
            items = self.client.chat_json_array(prompt)
            headlines = [str(x).strip() for x in items if str(x).strip()]
            if headlines:
                return headlines
        except Exception:
            pass
        # Deterministic fallback keeps calibration reproducible if the LLM fails.
        # In-profile paraphrases stay close to m0 so genuine drift stands out.
        return [
            f"The company continues its core activity: {company_profile}"
            for _ in range(k)
        ]


class AMLSynthesizer:
    """Cloud report-drafting agent (Stage 4)."""

    def __init__(self, client: GroqClient) -> None:
        self.client = client

    def synthesize(self, anomaly_trace: dict) -> str:
        """Draft the Markdown EDD report from a de-anonymised anomaly trace."""
        user_prompt = (
            "JSON de anomalias unificado (des-enmascarado) para el reporte EDD:\n\n"
            + json.dumps(anomaly_trace, ensure_ascii=False, indent=2)
        )
        return self.client.generate_report(AML_SYNTHESIZER_SYSTEM_PROMPT, user_prompt)
