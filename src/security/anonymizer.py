"""GDPR / Swiss Banking Law (Art. 47) masking proxy.

Sensitive identities (client names, directors, shareholders) are replaced by
opaque, reversible tokens before any text is sent to a cloud LLM. The reverse
mapping is held only in process memory at the bank perimeter, so the cloud
provider never observes a real identity. De-anonymisation happens locally,
immediately before a human compliance officer reads the final report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class DataAnonymizer:
    """Reversible pseudonymisation of sensitive entities.

    Tokens have the shape ``MASKED_<TYPE>_<NNN>`` and are stable for the
    lifetime of the instance: registering the same real name twice returns the
    same token, which keeps masked text internally consistent.
    """

    _mask_registry: dict[str, str] = field(default_factory=dict)
    _unmask_registry: dict[str, str] = field(default_factory=dict)
    _counter: int = 0

    def register_sensitive_entity(self, real_name: str, entity_type: str = "ENTITY") -> str:
        """Register a real identity and return its immutable masking token."""
        if not real_name or not real_name.strip():
            raise ValueError("Cannot mask an empty entity name.")
        if real_name in self._mask_registry:
            return self._mask_registry[real_name]

        self._counter += 1
        token = f"MASKED_{entity_type.upper()}_{self._counter:03d}"
        self._mask_registry[real_name] = token
        self._unmask_registry[token] = real_name
        return token

    def token_for(self, real_name: str) -> str | None:
        """Return the existing token for a name, or ``None`` if unregistered."""
        return self._mask_registry.get(real_name)

    def mask_text(self, text: str) -> str:
        """Replace every registered real name in ``text`` with its token.

        Names are substituted longest-first so that a shorter name (e.g. a
        director's surname) cannot corrupt a longer registered name that
        contains it.
        """
        if not text:
            return text
        masked = text
        for real_name, token in sorted(
            self._mask_registry.items(), key=lambda kv: len(kv[0]), reverse=True
        ):
            masked = re.sub(
                rf"\b{re.escape(real_name)}\b", token, masked, flags=re.IGNORECASE
            )
        return masked

    def unmask_text(self, masked_text: str) -> str:
        """Restore real identities on text produced by an external model."""
        if not masked_text:
            return masked_text
        restored = masked_text
        for token, real_name in self._unmask_registry.items():
            restored = restored.replace(token, real_name)
        return restored

    @property
    def registered_count(self) -> int:
        """Number of distinct sensitive entities currently masked."""
        return len(self._mask_registry)
