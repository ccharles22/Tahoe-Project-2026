"""
Application configuration with environment variable support.

Loads settings from .env / environment variables. See the project MkDocs
for the full list of configuration options.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()


def _get_int(name: str, default: int) -> int:
    """Retrieves integer from environment variable or return default."""
    val = os.getenv(name)
    return default if val is None else int(val)


def _get_float(name: str, default: float) -> float:
    """Retrieves float from environment variable or return default."""
    val = os.getenv(name)
    return default if val is None else float(val)


def _get_str(name: str, default: str) -> str:
    """Retrieves string from environment variable or return default."""
    val = os.getenv(name)
    return default if val is None else val

def _get_bool(name: str, default: bool) -> bool:
    """Retrieves boolean from environment variable or return default."""
    val = os.getenv(name)
    return default if val is None else val.lower() == "true"

@dataclass(frozen=True)
class Settings:
    """
    Application configuration settings with environment variable overrides.
    
    All attributes have sensible defaults but can be overridden via environment
    variables for different deployment contexts. Settings are frozen (immutable)
    to prevent accidental modification during runtime.
    """

    DATABASE_URL: str = _get_str("DATABASE_URL", "")

    GENETIC_CODE_TABLE: int = _get_int("GENETIC_CODE_TABLE", 11)
    STOP_POLICY: str = _get_str("STOP_POLICY", "truncate")

    MIN_MAPPING_IDENTITY_PCT: float = _get_float("MIN_MAPPING_IDENTITY_PCT", 95.0)
    MAX_X_FRACTION: float = _get_float("MAX_X_FRACTION", 0.05)
    LOG_EVERY_N: int = _get_int("LOG_EVERY_N", 10)
    DB_BATCH_SIZE: int = _get_int("DB_BATCH_SIZE", 25)

    WT_MIN_IDENTITY_PCT: float = 60.0
    MAX_ALIGNMENT_GAP_PENALTY: float = -10.0

    # Default to de novo remap fallback so future experiments keep working
    # when fixed-coordinate extraction drifts.
    FALLBACK_SEARCH: bool = _get_bool("FALLBACK_SEARCH", True)


# Global settings instance
settings = Settings()


if settings.STOP_POLICY not in {"truncate", "keep_stops"}:
    raise ValueError(
        f"Invalid STOP_POLICY '{settings.STOP_POLICY}'. "
        "Must be 'truncate' or 'keep_stops'."
    )

if not settings.DATABASE_URL:
    raise ValueError(
        "DATABASE_URL is not set. Export it as an environment variable, e.g.:\n"
        "  export DATABASE_URL='postgresql+psycopg://user:pass@host:5432/dbname'"
    )
