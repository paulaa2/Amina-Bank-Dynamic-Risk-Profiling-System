"""Engine configuration.

All tunables are read from environment variables (optionally loaded from a
``.env`` file at the project root) with documented defaults. The configuration
is intentionally self-contained so the engine can be reasoned about in
isolation from the data-collection layer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv is optional at runtime
    pass


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_DB_PATH = DATA_DIR / "risk_profiling.db"


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class EngineConfig:
    """Immutable runtime configuration for the pKYC engine."""

    # --- Persistence -------------------------------------------------------
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL")
        or f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"
    )

    # --- Local inference (Ollama) -----------------------------------------
    # Stage 2 runs locally and at zero monetary cost so sensitive identities
    # never leave the bank perimeter unmasked.
    ollama_host: str = field(
        default_factory=lambda: os.getenv("OLLAMA_HOST", "http://localhost:11434")
    )
    ollama_extractor_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_EXTRACTOR_MODEL", "qwen3:8b")
    )
    ollama_embedding_model: str = field(
        default_factory=lambda: os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text")
    )

    # --- Cloud inference (Groq) -------------------------------------------
    # Stage 4 is the only paid step and runs only on a confirmed statistical
    # alarm, on de-anonymised data, to draft the final compliance report.
    groq_api_key: str | None = field(default_factory=lambda: os.getenv("GROQ_API_KEY"))
    groq_report_model: str = field(
        default_factory=lambda: os.getenv("GROQ_REPORT_MODEL", "llama-3.3-70b-versatile")
    )

    # --- Statistical decision parameters ----------------------------------
    target_fwer: float = field(default_factory=lambda: _env_float("TARGET_FWER", 0.05))
    contagion_beta: float = field(default_factory=lambda: _env_float("CONTAGION_BETA", 0.5))
    combined_risk_threshold: float = field(
        default_factory=lambda: _env_float("COMBINED_RISK_THRESHOLD", 0.5)
    )

    # Page-Hinkley calibration multipliers (delta and alarm threshold in std).
    ph_delta_std: float = field(default_factory=lambda: _env_float("PH_DELTA_STD", 3.0))
    ph_threshold_std: float = field(default_factory=lambda: _env_float("PH_THRESHOLD_STD", 6.0))

    # Synthetic burn-in headlines generated at onboarding for cold-start.
    burn_in_size: int = field(default_factory=lambda: _env_int("BURN_IN_SIZE", 12))

    # --- Demo / throughput limits -----------------------------------------
    # Cap the number of Layer-1 events processed per run to keep the local
    # inference loop responsive during a live demo.
    max_events_per_run: int = field(
        default_factory=lambda: _env_int("MAX_EVENTS_PER_RUN", 12)
    )
    request_timeout: int = field(default_factory=lambda: _env_int("REQUEST_TIMEOUT", 120))

    # When True, inject a simulated transactional anomaly (dormancy break /
    # layering spike) into the behavioural stream. Off by default so the
    # default decision is driven by real public signals only.
    simulate_tx_anomaly: bool = field(
        default_factory=lambda: os.getenv("SIMULATE_TX_ANOMALY", "false").lower()
        in {"1", "true", "yes"}
    )

    # --- Approximate cost model (USD per 1M tokens) -----------------------
    # Used only for the cost-efficiency report. Local inference is free.
    groq_input_usd_per_mtok: float = field(
        default_factory=lambda: _env_float("GROQ_INPUT_USD_PER_MTOK", 0.59)
    )
    groq_output_usd_per_mtok: float = field(
        default_factory=lambda: _env_float("GROQ_OUTPUT_USD_PER_MTOK", 0.79)
    )

    def groq_enabled(self) -> bool:
        """True when a Groq key is configured for the paid report stage."""
        return bool(self.groq_api_key)


def load_config() -> EngineConfig:
    """Build an :class:`EngineConfig` from the current environment."""
    return EngineConfig()
