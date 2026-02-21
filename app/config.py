"""
Application configuration with environment variable support.

This module provides centralised configuration for the sequence processing pipeline,
with all settings exposed via environment variables for flexible deployment across
development, testing, and production environments.

Settings are loaded automatically from an .env file in the project root
(via python-dotenv) and can be overridden by real environment variables.

Configuration Categories:
    1. Database: PostgreSQL connection string
    2. Sequence Processing: Genetic code table, stop codon handling
    3. Quality Control: Identity thresholds, ambiguous base tolerance
    4. WT Mapping: Alignment thresholds and gap penalties
    5. Variant Processing: Optional fallback algorithms
    6. Job Logging: Progress reporting frequency

Environment Variables:
    - DATABASE_URL (required): PostgreSQL connection string (psycopg format).
    - GENETIC_CODE_TABLE: NCBI genetic code table number (default: 11 for bacterial)
    - STOP_POLICY: "truncate" (stop at first stop) or "keep_stops" (default: truncate)
    - MIN_MAPPING_IDENTITY_PCT: Minimum percent identity for WT mapping (default: 95.0)
    - MAX_X_FRACTION: Maximum allowed unknown residues fraction (default: 0.05)
    - LOG_EVERY_N: Log progress for every N variants (default: 10)
    - FALLBACK_SEARCH: Enables de novo search on variant extraction failure (default: false)

Usage:
    from app.config import settings

    engine = create_engine(settings.DATABASE_URL)
    translate_dna(seq, table=settings.GENETIC_CODE_TABLE)
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

    WT_MIN_IDENTITY_PCT: float = 60.0
    MAX_ALIGNMENT_GAP_PENALTY: float = -10.0

    FALLBACK_SEARCH: bool = _get_bool("FALLBACK_SEARCH", False)


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