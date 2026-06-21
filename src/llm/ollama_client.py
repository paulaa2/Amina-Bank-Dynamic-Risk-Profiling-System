"""Local inference client (Ollama).

Wraps the local Ollama server for the two zero-cost stages of the pipeline:
structured chat completion (fact extraction, entity resolution) and text
embeddings (semantic drift). All sensitive data stays on this local boundary.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass

import ollama

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)


@dataclass
class LocalUsage:
    """Token accounting for a single local call (free, tracked for reporting)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0


def _strip_to_json(raw: str) -> str:
    """Best-effort extraction of a JSON payload from a model response."""
    text = (raw or "").strip()
    text = _JSON_FENCE.sub("", text).strip()
    return text


class OllamaClient:
    """Thin, resilient wrapper around the Ollama Python client."""

    def __init__(
        self,
        host: str = "http://localhost:11434",
        chat_model: str = "llama3",
        embedding_model: str = "nomic-embed-text",
        timeout: int = 120,
    ) -> None:
        self.host = host
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        self._client = ollama.Client(host=host, timeout=timeout)
        self.last_usage = LocalUsage()
        # Thinking models (e.g. qwen3) reason before answering, which adds heavy
        # latency and token cost. Disable it for deterministic, fast JSON. The
        # flag self-heals to False if the configured model rejects the option.
        self._disable_thinking = True
        # Keep models resident between calls so repeated demos stay warm.
        self._keep_alive = "10m"

    def available(self) -> bool:
        """Return True if the Ollama server responds to a model listing."""
        try:
            self._client.list()
            return True
        except Exception:
            return False

    def chat_json(self, system_prompt: str, user_prompt: str) -> dict:
        """Run a chat completion constrained to a JSON object and parse it."""
        response = self._chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
        )
        self._record_usage(response)
        content = response["message"]["content"]
        return self._parse_json(content, _JSON_OBJECT)

    def chat_json_array(self, prompt: str) -> list:
        """Run a chat completion expected to return a JSON array of strings."""
        response = self._chat(
            [{"role": "user", "content": prompt}],
            temperature=0.2,
        )
        self._record_usage(response)
        content = response["message"]["content"]
        parsed = self._parse_json(content, _JSON_ARRAY)
        return self._coerce_string_list(parsed)

    @staticmethod
    def _coerce_string_list(parsed) -> list:
        """Extract a list of strings from varied model JSON shapes.

        Handles a bare array, an object wrapping an array under any key, and the
        qwen3 ``format=json`` quirk where items become object keys with empty
        values (e.g. ``{"headline one": "", "headline two": ""}``).
        """
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if str(x).strip()]
        if isinstance(parsed, dict):
            for value in parsed.values():
                if isinstance(value, list) and value:
                    return [str(x).strip() for x in value if str(x).strip()]
            keys = [k for k in parsed.keys() if isinstance(k, str) and len(k) > 12]
            if keys:
                return keys
            vals = [v for v in parsed.values() if isinstance(v, str) and len(v) > 12]
            return vals
        return []

    def embed(self, text: str) -> list[float]:
        """Return the embedding vector for ``text``."""
        response = self._client.embeddings(
            model=self.embedding_model, prompt=text, keep_alive=self._keep_alive
        )
        return list(response["embedding"])

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a sequence of texts (sequential; Ollama is local)."""
        return [self.embed(t) for t in texts]

    # -- internals ---------------------------------------------------------

    def _chat(self, messages: list[dict], temperature: float):
        """Chat with JSON formatting, disabling model reasoning when supported."""
        kwargs = dict(
            model=self.chat_model,
            messages=messages,
            format="json",
            options={"temperature": temperature},
            keep_alive=self._keep_alive,
        )
        if self._disable_thinking:
            try:
                return self._client.chat(think=False, **kwargs)
            except Exception:
                # The configured model does not accept the think option; fall
                # back permanently and retry without it.
                self._disable_thinking = False
        return self._client.chat(**kwargs)

    def _record_usage(self, response) -> None:
        prompt_tokens = int(response.get("prompt_eval_count", 0) or 0)
        completion_tokens = int(response.get("eval_count", 0) or 0)
        self.last_usage = LocalUsage(prompt_tokens, completion_tokens)

    @staticmethod
    def _parse_json(content: str, fallback_pattern: re.Pattern):
        text = _strip_to_json(content)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            match = fallback_pattern.search(text)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
        return {}
