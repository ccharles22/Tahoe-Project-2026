from __future__ import annotations

from dataclasses import dataclass
import os

def _get_int(name: str, default: int) -> int:
    val = os.getenv(name)
    return default if val is None else int(val)

def _get_float(name: str, default: float) -> float:
    val = os.getenv(name)
    return default if val is None else float(val)

def _get_str(name: str, default: str) -> str:
    val = os.getenv(name)
    return default if val is None else val

@dataclass(frozen=True)
class Settings:
    # Database
    DATABASE_URL: str = _get_str("DATABASE_URL", "postgresql+psycopg://patriciaosire:blue@100.80.183.102:5432/bio727p_group_project")
    
    # Sequence processing policies 
    GENETIC_CODE_TABLE: int = _get_int("GENETIC_CODE_TABLE", "11")
    STOP_POLICY: str = _get_str("STOP_POLICY", "truncate")

    # QC / acceptance thresholds 
    MIN_MAPPING_IDENTITY_PCT: float= _get_float("MIN_MAPPING_IDENTITY_PCT", 95.0)
    MAX_X_FRACTION: float = _get_float("MAX_X_FRACTION", 0.05) # 5% unknown residues

    # Job logging
    LOG_EVERY_N: int = _get_int("LOG_EVERY_N", 10)

    # WT mapping
    WT_MIN_IDENTITY_PCT: float = 60.0
    MAX_ALIGNMENT_GAP_PENALTY: float = -10.0

settings = Settings()

# Configuration validation
if settings.STOP_POLICY not in {"truncate", "keep_stops"}:
    raise ValueError(
        f"Invalid STOP_POLICY '{settings.STOP_POLICY}'."
        "Must be 'truncate' or 'keep_stops'."
    )