from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "mysql+pymysql://root:password@localhost:3306/app_db")
    # for Ecoli use 11, for Human use 1
    GENETIC_CODE_TABLE: int = int(os.getenv("GENETIC_CODE_TABLE", "1"))
    # Translation policy: "truncate" or "keep_stops"
    STOP_POLICY: str = os.getenv("STOP_POLICY", "truncate")
    # If variant extraction fails QC, optionally re-run slower gene finding
    FALLBACK_SEARCH: bool = os.getenv("FALLBACK_SEARCH","true").lower() in {"1", "true", "yes"}

settings = Settings()