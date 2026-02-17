"""
Application configuration with environment variable support.

This module provides centralised configuration for the sequence processing pipeline,
with all settings exposed via environment variables for flexible deployment across
development, testing, and production environments.

Configuration Categories:
    1. Database: PostgreSQL connection string
    2. Sequence Processing: Genetic code table, stop codon handling
    3. Quality Control: Identity thresholds, ambiguous base tolerance
    4. WT Mapping: Alignment thresholds and gap penalties
    5. Variant Processing: Optional fallback algorithms
    6. Job Logging: Progress reporting frequency

Environment Variables:
    All settings can be overridden via environment variables:
    - DATABASE_URL: PostgreSQL connection string (psycopg format)
    - GENETIC_CODE_TABLE: NCBI genetic code table number (default: 11 for bacterial)
    - STOP_POLICY: "truncate" (stop at first stop) or "keep_stops" (default: truncate)
    - MIN_MAPPING_IDENTITY_PCT: Minimum percent identity for WT mapping (default: 95.0)
    - MAX_X_FRACTION: Maximum allowed unknown residues fraction (default: 0.05)
    - LOG_EVERY_N: Log progress every N variants (default: 10)
    - FALLBACK_SEARCH: Enable de novo search on variant extraction failure (default: false)

Usage:
    from app.config import settings
    
    # Access configuration
    engine = create_engine(settings.DATABASE_URL)
    translate_dna(seq, table=settings.GENETIC_CODE_TABLE)
"""

from __future__ import annotations

from dataclasses import dataclass
import os


def _get_int(name: str, default: int) -> int:
    """Retrieve integer from environment variable or return default."""
    val = os.getenv(name)
    return default if val is None else int(val)


def _get_float(name: str, default: float) -> float:
    """Retrieve float from environment variable or return default."""
    val = os.getenv(name)
    return default if val is None else float(val)


def _get_str(name: str, default: str) -> str:
    """Retrieve string from environment variable or return default."""
    val = os.getenv(name)
    return default if val is None else val


def _default_database_url() -> str:
    """Build a sensible local PostgreSQL DSN from docker-style environment variables."""
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "postgres")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "tahoe_dev")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"


@dataclass(frozen=True)
class Settings:
    """
    Application configuration settings with environment variable overrides.
    
    All attributes have sensible defaults but can be overridden via environment
    variables for different deployment contexts. Settings are frozen (immutable)
    to prevent accidental modification during runtime.
    """
    
    # ========================================================================
    # Database Configuration
    # ========================================================================
    DATABASE_URL: str = _get_str(
        "DATABASE_URL", 
        _default_database_url()
    )  # PostgreSQL connection string (psycopg driver)
    
    # ========================================================================
    # Sequence Processing Policies
    # ========================================================================
    GENETIC_CODE_TABLE: int = _get_int("GENETIC_CODE_TABLE", "11")
    # NCBI genetic code table: 11 = bacterial/archaeal/plant plastid
    # See: https://www.ncbi.nlm.nih.gov/Taxonomy/Utils/wprintgc.cgi
    
    STOP_POLICY: str = _get_str("STOP_POLICY", "truncate")
    # Stop codon handling:
    #   "truncate" - stop translation at first stop codon
    #   "keep_stops" - include stop codons (*) in translated sequence


    # Quality Control & Acceptance Thresholds
    MIN_MAPPING_IDENTITY_PCT: float = _get_float("MIN_MAPPING_IDENTITY_PCT", 95.0)
    # Minimum percent identity for accepting sequence alignments
    
    MAX_X_FRACTION: float = _get_float("MAX_X_FRACTION", 0.05)
    # Maximum allowed fraction of unknown/ambiguous residues (default: 5%)

    # Job Logging
    LOG_EVERY_N: int = _get_int("LOG_EVERY_N", 10)
    # Report progress every N variants processed (for monitoring long jobs)


    # WT Mapping Configuration
    WT_MIN_IDENTITY_PCT: float = 60.0
    # Minimum identity threshold for 6-frame WT gene search
    # Lower than MIN_MAPPING_IDENTITY_PCT to allow for more distant sequences
    
    MAX_ALIGNMENT_GAP_PENALTY: float = -10.0
    # Gap opening penalty for protein alignments (negative = penalty)

    # Variant Processing Options
    FALLBACK_SEARCH: bool = _get_str("FALLBACK_SEARCH", "false").lower() == "true"
    # Enable de novo 6-frame search if variant CDS extraction fails using WT coordinates
    # (Currently placeholder - not fully implemented)


# Global settings instance
settings = Settings()


# ============================================================================
# Configuration Validation
# ============================================================================

# Validate STOP_POLICY at module load time
if settings.STOP_POLICY not in {"truncate", "keep_stops"}:
    raise ValueError(
        f"Invalid STOP_POLICY '{settings.STOP_POLICY}'. "
        "Must be 'truncate' or 'keep_stops'."
    )