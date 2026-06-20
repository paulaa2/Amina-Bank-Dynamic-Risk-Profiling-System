"""AMINA Bank - Secure Perpetual KYC (pKYC) & Multi-Stream Drift Engine.

This package contains the risk-intelligence engine for the SwissHacks 2026
Dynamic Risk Profiling challenge. It is deliberately kept separate from the
data-collection layer in ``scripts/`` (the public-source collectors and API
clients). The engine consumes the SQLite database produced by that layer as its
single integration boundary and never calls external collection APIs directly.

High-level flow (see :mod:`src.pipeline`)::

    Layer 1 (public signals) + Layer 2 (internal KYC baseline)
        -> Stage 1  deterministic NER triage        (free)
        -> Stage 2  GDPR masking + local extraction  (Ollama, free)
        -> Stage 3  statistical + graph math         (pure Python, free)
        -> Stage 4  AML report on alarm only         (Groq, paid)
        -> four-eyes governance + audit trail
"""

from __future__ import annotations

__version__ = "1.0.0"
