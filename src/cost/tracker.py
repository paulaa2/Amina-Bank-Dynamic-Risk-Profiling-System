"""Token-usage and cost accounting.

Cost efficiency is an explicit judging criterion. The tracker separates free
local inference (Ollama) from paid cloud inference (Groq), records how many
events were filtered at each stage, and projects the cost per 1,000 analyses so
the staged "lazy execution" design can be quantified.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CostTracker:
    """Accumulates token usage and stage counters for one engine run."""

    groq_input_usd_per_mtok: float = 0.59
    groq_output_usd_per_mtok: float = 0.79

    local_prompt_tokens: int = 0
    local_completion_tokens: int = 0
    cloud_prompt_tokens: int = 0
    cloud_completion_tokens: int = 0

    events_seen: int = 0
    events_passed_triage: int = 0
    events_embedded: int = 0
    cloud_reports: int = 0

    _stage_calls: dict[str, int] = field(default_factory=dict)

    def add_local(self, prompt_tokens: int, completion_tokens: int, label: str = "local") -> None:
        self.local_prompt_tokens += int(prompt_tokens)
        self.local_completion_tokens += int(completion_tokens)
        self._stage_calls[label] = self._stage_calls.get(label, 0) + 1

    def add_cloud(self, prompt_tokens: int, completion_tokens: int, label: str = "groq_report") -> None:
        self.cloud_prompt_tokens += int(prompt_tokens)
        self.cloud_completion_tokens += int(completion_tokens)
        self.cloud_reports += 1
        self._stage_calls[label] = self._stage_calls.get(label, 0) + 1

    @property
    def cloud_cost_usd(self) -> float:
        return (
            self.cloud_prompt_tokens / 1_000_000 * self.groq_input_usd_per_mtok
            + self.cloud_completion_tokens / 1_000_000 * self.groq_output_usd_per_mtok
        )

    def cost_per_1000_analyses(self) -> float:
        """Project cloud cost to 1,000 analysed events at the current ratio."""
        if self.events_seen == 0:
            return 0.0
        return self.cloud_cost_usd / self.events_seen * 1000

    def summary(self) -> dict:
        return {
            "events_seen": self.events_seen,
            "events_passed_triage": self.events_passed_triage,
            "events_embedded": self.events_embedded,
            "cloud_reports_generated": self.cloud_reports,
            "local_tokens": {
                "prompt": self.local_prompt_tokens,
                "completion": self.local_completion_tokens,
                "cost_usd": 0.0,
            },
            "cloud_tokens": {
                "prompt": self.cloud_prompt_tokens,
                "completion": self.cloud_completion_tokens,
                "cost_usd": round(self.cloud_cost_usd, 6),
            },
            "projected_cloud_cost_per_1000_analyses_usd": round(
                self.cost_per_1000_analyses(), 4
            ),
            "stage_calls": dict(self._stage_calls),
        }
