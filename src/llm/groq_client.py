"""Cloud inference client (Groq).

Used exclusively by Stage 4 to draft the final EDD compliance report on a
confirmed statistical alarm. This is the only paid step in the pipeline, so
token usage is captured for the cost-efficiency report.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CloudUsage:
    """Token accounting for a single cloud call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0


class GroqClient:
    """Thin wrapper around the Groq chat-completions API."""

    def __init__(self, api_key: str, model: str = "llama-3.3-70b-versatile") -> None:
        if not api_key:
            raise ValueError("A Groq API key is required for the report stage.")
        from groq import Groq  # imported lazily so the engine loads without it

        self.model = model
        self._client = Groq(api_key=api_key)
        self.last_usage = CloudUsage()

    def generate_report(self, system_prompt: str, user_prompt: str) -> str:
        """Generate the Markdown compliance report and record token usage."""
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.last_usage = CloudUsage(
                prompt_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                completion_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            )
        return response.choices[0].message.content or ""
