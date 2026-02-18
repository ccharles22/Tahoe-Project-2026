"""
UniProt API client for retrieving reference protein sequences and annotations.

This module provides a robust interface to the UniProt REST API with:
- Automatic retry logic with linear backoff for transient failures
- Dual-endpoint fallback (primary and legacy URLs)
- Comprehensive error handling with user-friendly messages
- FASTA and JSON format support for different use cases
- Protein sequence validation and feature extraction

Key Functions:
    - acquire_uniprot_protein_fasta(): Fast sequence-only retrieval via FASTA endpoint
    - acquire_uniprot_entry_with_features(): Full entry with metadata and features via JSON endpoint

Retry Strategy:
    - Default: 2 retries with 1.5s linear backoff per attempt
    - Retries triggered by: network errors, HTTP 429 (rate limit), HTTP 5xx (server errors)
    - Non-retryable: HTTP 404 (not found), HTTP 4xx (other client errors)

Error Handling:
    All retrieval failures raise UniProtRetrievalError with context about:
    - Invalid accession format
    - Network/timeout issues
    - API errors (404, 429, 5xx)
    - Invalid or unparseable sequences

Data Validation:
    - Accession: 3-20 alphanumeric characters (not full UniProt spec, but catches common errors)
    - Sequence: Standard amino acid alphabet + ambiguity codes (X, B, Z, J, U, O) + stop codon (*)

Usage:
    from app.services.sequence.uniprot_service import acquire_uniprot_protein_fasta
    
    # Fast sequence retrieval
    sequence = acquire_uniprot_protein_fasta("P12345")
    
    # Full entry with features
    entry = acquire_uniprot_entry_with_features("P12345")
    print(entry.protein_name, entry.features)
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import re
import time
from typing import Any, Final, Iterable, Optional

import requests


# ============================================================================
# API Configuration
# ============================================================================

# UniProt REST API endpoints (2024+ format)
UNIPROT_FASTA_URL: Final[str] = "https://rest.uniprot.org/uniprotkb/{accession}.fasta"
UNIPROT_JSON_URL: Final[str] = "https://rest.uniprot.org/uniprotkb/{accession}.json"

# Legacy endpoint as fallback for compatibility
UNIPROT_JSON_URL_FALLBACK: Final[str] = "https://www.uniprot.org/uniprot/{accession}?format=json"

# Request timeout: 15 seconds balances responsiveness with network latency tolerance
DEFAULT_TIMEOUT_S: Final[int] = 15

# Retry configuration: 2 retries allows recovery from transient network/server issues
# without excessive delay (total max time: 15s + 1.5s + 3s = 19.5s)
DEFAULT_RETRIES: Final[int] = 2
RETRY_BACKOFF_S: Final[float] = 1.5  # Linear backoff: attempt 1 = 1.5s, attempt 2 = 3s


# ============================================================================
# Validation Patterns
# ============================================================================

# Standard amino acids + ambiguity codes + stop codon
# X=unknown, B=Asn/Asp, Z=Gln/Glu, J=Leu/Ile, U=selenocysteine, O=pyrrolysine
AMINO_ACID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[ACDEFGHIKLMNPQRSTVWYXBZJUO\*]+$"
)

# Accession format: 3-20 alphanumeric characters (simplified, not full UniProt spec)
# Catches common user errors while allowing all valid UniProt accession formats
ACCESSION_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Z0-9]{3,20}$")


# ============================================================================
# Exceptions
# ============================================================================

class UniProtRetrievalError(Exception):
    """
    Raised when UniProt data cannot be retrieved, parsed, or validated.
    
    Common causes:
        - Invalid accession format
        - Accession not found (HTTP 404)
        - Network/timeout errors
        - Rate limiting (HTTP 429)
        - Server errors (HTTP 5xx)
        - Invalid/unparseable sequence data
    """


# ============================================================================
# Data Models
# ============================================================================

@dataclass(frozen=True)
class UniProtFeature:
    """
    A single protein feature annotation from UniProt.
    
    Represents structural or functional annotations such as domains,
    binding sites, post-translational modifications, variants, etc.
    
    Attributes:
        feature_type: Feature category (e.g., "Domain", "Active site", "Mutagenesis").
        description: Human-readable description of the feature (may be None).
        begin: Start position (1-based inclusive, may be None for non-positional features).
        end: End position (1-based inclusive, may be None for point features).
        evidence: Evidence code or source supporting this annotation (optional).
    """
    feature_type: str
    description: Optional[str]
    begin: Optional[int]  # 1-based inclusive
    end: Optional[int]    # 1-based inclusive
    evidence: Optional[str] = None


@dataclass(frozen=True)
class UniProtEntry:
    """
    Complete UniProt entry with protein sequence and metadata.
    
    Contains all information typically needed for bioinformatics analysis:
    sequence data, identifiers, organism information, and feature annotations.
    
    Attributes:
        accession: UniProt accession number (e.g., "P12345").
        sequence: Full amino acid sequence (uppercase, no whitespace).
        length: Sequence length in amino acids.
        protein_name: Recommended or submitted protein name (may be None).
        gene_name: Primary gene name if available (may be None).
        organism: Scientific organism name (e.g., "Homo sapiens").
        features: Tuple of all annotated features for this protein.
    """
    accession: str
    sequence: str
    length: int
    protein_name: Optional[str]
    gene_name: Optional[str]
    organism: Optional[str]
    features: tuple[UniProtFeature, ...]


# ============================================================================
# Public API - Sequence Retrieval
# ============================================================================


def acquire_uniprot_protein_fasta(
        accession: str,
        *,
        timeout: int = DEFAULT_TIMEOUT_S,
        retries: int = DEFAULT_RETRIES,
        session: Optional[requests.Session] = None
) -> str:
    """
    Retrieve protein sequence from UniProt FASTA endpoint.
    
    Fast, lightweight retrieval when only the sequence is needed (no metadata).
    Automatically validates accession format and sequence content.
    
    Args:
        accession: UniProt accession number (e.g., "P12345", case-insensitive).
        timeout: HTTP request timeout in seconds (default: 15).
        retries: Number of retry attempts on transient failures (default: 2).
        session: Optional requests.Session for connection pooling (useful for bulk retrieval).
    
    Returns:
        str: Protein sequence as uppercase amino acid string (no whitespace or header).
    
    Raises:
        UniProtRetrievalError: If accession is invalid, not found, or sequence is unparseable.
    
    """
    accession = _clean_accession(accession)
        
    text = _http_get_text(
        url=UNIPROT_FASTA_URL.format(accession=accession),
        accept="text/x-fasta",
        timeout=timeout,
        retries=retries,
        session=session,
    )
    seq = _parse_fasta_sequence(text)
    if not seq:
        raise UniProtRetrievalError(
            f"Failed to parse a valid protein sequence from UniProt FASTA for '{accession}'."
         )
    if not AMINO_ACID_PATTERN.match(seq):
        raise UniProtRetrievalError(
            f"Invalid protein sequence retrieved from UniProt FASTA for '{accession}'."
        )
    return seq

def acquire_uniprot_entry_with_features(
        accession: str,
        *,
        timeout: int = DEFAULT_TIMEOUT_S,
        retries: int = DEFAULT_RETRIES,
        session: Optional[requests.Session] = None
) -> UniProtEntry:
    """
    Retrieve complete UniProt entry with sequence, metadata, and features.
    
    Fetches comprehensive protein information from UniProt JSON endpoint,
    including sequence, organism details, protein/gene names, and all
    annotated features (domains, sites, PTMs, etc.).
    
    Args:
        accession: UniProt accession number (e.g., "P12345", case-insensitive).
        timeout: HTTP request timeout in seconds (default: 15).
        retries: Number of retry attempts on transient failures (default: 2).
        session: Optional requests.Session for connection pooling.
    
    Returns:
        UniProtEntry: Complete entry with sequence, metadata, and feature list.
    
    Raises:
        UniProtRetrievalError: If accession is invalid, not found, or data is unparseable.
    
    """
    accession = _clean_accession(accession)

    data = _http_get_json(
        primary_url=UNIPROT_JSON_URL.format(accession=accession),
        fallback_url=UNIPROT_JSON_URL_FALLBACK.format(accession=accession),
        timeout=timeout,
        retries=retries,
        session=session,
    )

    seq = _extract_sequence_from_json(data)
    if not seq:
        raise UniProtRetrievalError(
            f"Failed to extract a valid protein sequence from UniProt JSON for '{accession}'."
        )
    if not AMINO_ACID_PATTERN.match(seq):
        raise UniProtRetrievalError(
            f"Invalid protein sequence extracted from UniProt JSON for '{accession}'."
        )

    protein_name = _safe_get(
        data,
        ("proteinDescription", "recommendedName", "fullName", "value"),
    ) or _safe_get(
        data,
        ("proteinDescription", "submittedName", 0, "fullName", "value"),
    )
         
    gene_name = _safe_get(data, ("genes", 0, "geneName", "value"))
    organism = _safe_get(data, ("organism", "scientificName"))

    feats = tuple(_extract_features_from_json(data.get("features", [])))

    return UniProtEntry(
        accession=accession,
        sequence=seq,
        length=len(seq),
        protein_name=protein_name,
        gene_name=gene_name,
        organism=organism,
        features=feats,
    )


# ============================================================================
# Private Helpers - Validation & HTTP
# ============================================================================

def _clean_accession(accession: str) -> str:
    """
    Validate and normalize UniProt accession.
    
    Args:
        accession: Raw accession string (may have whitespace or mixed case).
    
    Returns:
        str: Cleaned accession (uppercase, trimmed).
    
    Raises:
        UniProtRetrievalError: If accession is empty or has invalid format.
    """
    acc = (accession or "").strip().upper()
    if not acc:
        raise UniProtRetrievalError("UniProt accession must be a non-empty string.")
    if not ACCESSION_PATTERN.match(acc):
        raise UniProtRetrievalError(f"Invalid UniProt accession format: '{acc}'")
    return acc

def _http_get_text(
        *, 
        url: str,
        accept: str,
        timeout: int,
        retries: int,
        session: Optional[requests.Session],
) -> str:
    """
    Perform HTTP GET with retry logic for text-based responses.
    
    Implements automatic retry with linear backoff for transient failures.
    Retries are triggered by network errors, rate limiting, and server errors.
    
    Args:
        url: Full URL to request.
        accept: Accept header value (e.g., "text/x-fasta", "application/json").
        timeout: Request timeout in seconds.
        retries: Number of retry attempts after initial failure.
        session: Optional requests.Session (created if None).
    
    Returns:
        str: Response body as text.
    
    Raises:
        UniProtRetrievalError: If all attempts fail or non-retryable error occurs.
    """
    s = session or requests.Session()
    headers = {
        "User-Agent": "Tahoe-Project-2026/1.0 (MSc Bioinformatics Group Project)",
        "Accept": accept,
    }

    last_exc: Optional[Exception] = None
    for attempt in range (retries + 1):
        try:
            resp= s.get(url, headers=headers, timeout=timeout)
            _raise_for_uniprot_status(resp)
            return resp.text
        except (requests.RequestException, UniProtRetrievalError) as exc:
            last_exc = exc
            if attempt < retries and _is_retryable(exc):
                time.sleep(RETRY_BACKOFF_S * (attempt + 1))
                continue
            break

    raise UniProtRetrievalError(f"Failed to retrieve UniProt data from '{url}'.") from last_exc

def _http_get_json(
        *,
        primary_url: str,
        fallback_url: str,
        timeout: int,
        retries: int,
        session: Optional[requests.Session],
) -> dict[str, Any]:
    """
    Retrieves and parses JSON with dual-endpoint fallback.
    
    Attempts primary URL first, then falls back to legacy endpoint if needed.
    This handles UniProt API transitions and improves reliability.
    
    Args:
        primary_url: Modern UniProt REST API endpoint.
        fallback_url: Legacy endpoint for backward compatibility.
        timeout: Request timeout in seconds.
        retries: Number of retry attempts per endpoint.
        session: Optional requests.Session.
    
    Returns:
        dict: Parsed JSON response.
    
    Raises:
        UniProtRetrievalError: If both endpoints fail or JSON is unparseable.
    """
    text_exc: Optional[Exception] = None

    for url in (primary_url, fallback_url):
        try:
            raw = _http_get_text(url=url, accept="application/json", timeout=timeout,
                                 retries=retries, session=session)
            return json.loads(raw)
        except (UniProtRetrievalError, json.JSONDecodeError) as exc:
            text_exc = exc
            continue
    
    raise UniProtRetrievalError("Failed to retrieve or parse UniProt JSON data.") from text_exc


# ============================================================================
# Private Helpers - Parsing & Extraction
# ============================================================================

def _raise_for_uniprot_status(resp: requests.Response) -> None:
    """
    Checks HTTP response status and raises user-friendly errors.
    
    Translates HTTP status codes into specific error messages with
    actionable guidance for the user.
    
    Args:
        resp: requests.Response object to check.
    
    Raises:
        UniProtRetrievalError: For any non-200 status code with context-specific message.
    """
    code = resp.status_code
    
    if code == 200:
        return
    if code == 404:
        raise UniProtRetrievalError("UniProt accession not found (HTTP 404).")
    if code == 429:
        raise UniProtRetrievalError("UniProt rate limit exceeded (HTTP 429). Try again later.")
    if 500 <= code <= 599:
        raise UniProtRetrievalError(f"UniProt server error (HTTP {code}). Try again later.")
    
    raise UniProtRetrievalError(f"Unexpected HTTP response from UniProt: {code}.")

def _is_retryable(exc: Exception) -> bool:
    """
    Determines if an exception is worth retrying.
    
    Retry strategy:
        - Network errors: Yes (timeout, connection issues)
        - Rate limit (429): Yes (might clear after backoff)
        - Server errors (5xx): Yes (transient server issues)
        - Client errors (404, 400): No (won't succeed on retry)
    
    Args:
        exc: Exception caught during HTTP request.
    
    Returns:
        bool: True if retry is likely to succeed, False otherwise.
    """
    if isinstance(exc, UniProtRetrievalError):
        msg = str(exc)
        return ("rate limit" in msg.lower()) or ("server error" in msg.lower())
    return True  # Network errors (timeout, connection) are retryable

def _parse_fasta_sequence(fasta_text: str) -> str:
    """
    Extract sequence from FASTA format text.
    
    Handles standard FASTA format:
        >header line
        SEQUENCE
        LINE2
        ...
    
    Args:
        fasta_text: Raw FASTA string from UniProt.
    
    Returns:
        str: Concatenated sequence (uppercase, no whitespace), or empty string if invalid.
    """
    if not fasta_text:
        return ""
    
    lines = [ln.strip() for ln in fasta_text.splitlines() if ln.strip()]
    if not lines or not lines[0].startswith(">"):
        return ""
    
    seq = "".join(lines[1:]).replace(" ", "").upper()
    return seq

def _extract_sequence_from_json(data: dict[str, Any]) -> str:
    """
    Extract protein sequence from UniProt JSON response.
    
    Navigates JSON structure to find sequence value at standard location:
    {"sequence": {"value": "MTEYKLVVV..."}}
    
    Args:
        data: Parsed UniProt JSON response.
    
    Returns:
        str: Protein sequence (uppercase, trimmed), or empty string if not found.
    """
    seq = _safe_get(data, ("sequence", "value"))
    return str(seq).upper().strip() if isinstance(seq, str) else ""

def _extract_features_from_json(features: Iterable[Any]) -> Iterable[UniProtFeature]:
    """
    Parse feature annotations from UniProt JSON.
    
    Extracts feature type, description, location, and evidence from the
    "features" array in UniProt JSON responses. Handles various location
    formats and missing fields gracefully.
    
    Args:
        features: List of feature dictionaries from UniProt JSON.
    
    Yields:
        UniProtFeature: Parsed feature objects (skips malformed entries).
    """
    for f in features:
        if not isinstance(f, dict):
            continue

        ftype = f.get("type")
        if not isinstance(ftype, str) or not ftype:
            continue

        desc = f.get("description") if isinstance(f.get("description"), str) else None

        # Location shape can vary; handle the most common:
        # {"location": {"start": {"value": 1}, "end": {"value": 10}}}
        begin = _safe_get(f, ("location", "start", "value"))
        end = _safe_get(f, ("location", "end", "value"))

        begin_i = int(begin) if isinstance(begin, (int, float, str)) and str(begin).isdigit() else None
        end_i = int(end) if isinstance(end, (int, float, str)) and str(end).isdigit() else None

        evidence = None
        ev = f.get("evidences")
        if isinstance(ev, list) and ev:
            evidence = str(ev[0].get("evidenceCode") or ev[0].get("source") or "")

        yield UniProtFeature(
            feature_type=ftype,
            description=desc,
            begin=begin_i,
            end=end_i,
            evidence=evidence or None
        )

def _safe_get(obj: Any, path: tuple[Any, ...]) -> Any:
    """
    Safely traverse nested dict/list structure.
    
    Navigates through nested JSON structures without raising KeyError or
    IndexError. Useful for extracting optional fields from API responses.
    
    Args:
        obj: Root object (typically dict or list).
        path: Tuple of keys (str) and indices (int) defining traversal path.
    
    Returns:
        Any: Value at specified path, or None if path is invalid at any step.
    
    """
    current = obj
    for p in path:
        if isinstance(current, dict) and isinstance(p, str):
            current = current.get(p)
        elif isinstance(current, list) and isinstance(p, int) and 0 <= p < len(current):
            current = current[p]
        else:
            return None
    return current












