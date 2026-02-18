"""
DNA/protein sequence utility functions for bioinformatics workflows.

This module provides foundational sequence manipulation and quality control
functions used throughout the sequence processing pipeline:

1. DNA Normalisation: Standardise input sequences (whitespace removal, uppercase)
2. Translation: DNA to protein with configurable genetic code and stop codon handling
3. Quality Control: Detect ambiguous bases, frameshifts, premature stops
4. Strand Operations: Reverse complement for minus-strand genes
5. Circular DNA: Handle genes spanning plasmid origin (wrap-around coordinates)

Key Functions:
    - translate_dna(): Simple DNA→protein translation (Biopython wrapper)
    - translate_cds_with_qc(): Translation with comprehensive QC checks
    - circular_slice(): Extract subsequences from circular plasmids
    - normalise_dna(): Standardise DNA input format

Quality Control:
    TranslationQC dataclass captures:
    - Ambiguous bases (N, R, Y, etc.) from low-confidence assemblies
    - Frameshifts (length not divisible by 3)
    - Premature stop codons
    - Truncation events

Usage:
    from app.utils.seq_utils import translate_cds_with_qc, circular_slice
    
    # Translate with QC
    protein, qc = translate_cds_with_qc(cds, genetic_code_table=11)
    if qc.has_frameshift:
        print("Warning: frameshift detected")
    
    # Extract gene spanning plasmid origin
    gene = circular_slice(plasmid, start=4500, end=150)  # wraps around
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Set, Tuple
from Bio.Seq import Seq


# ============================================================================
# Constants - DNA Validation
# ============================================================================

# Standard unambiguous DNA bases (A, C, G, T)
# Used for strict quality control - sequences with other bases are flagged
VALID_DNA: Set[str] = {"A", "C", "G", "T"}

# IUPAC ambiguous nucleotide codes commonly produced by sequence assemblers
# N=any, R=purine, Y=pyrimidine, W=weak, S=strong, K=keto, M=amino,
# B=not A, D=not C, H=not G, V=not T
AMBIGUOUS_BASES: Set[str] = set("NRYWSKMBDHV")


# ============================================================================
# Data Models
# ============================================================================

@dataclass(frozen=True)
class TranslationQC:
    """
    Quality control metrics for in-silico translation results.
    
    Captures all issues that may affect downstream analysis, enabling
    automated filtering and manual review of problematic sequences.
    
    Attributes:
        normalised_len: Length of normalised DNA sequence (nt, after whitespace removal).
        has_ambiguous_bases: True if sequence contains non-ACGT bases (N, R, Y, etc.).
        has_stop_codon: True if stop codon (*) found anywhere in translated protein.
        has_frameshift: True if DNA length not divisible by 3 (incomplete codon).
        is_truncated: True if translation stopped early due to stop codon (stop_policy="truncate").
        stop_index: 0-based position of first stop codon in protein (None if no stop).
        notes: Human-readable warnings or error messages (None if no issues).
    
    """
    normalised_len: int
    has_ambiguous_bases: bool
    has_stop_codon: bool    
    has_frameshift: bool
    is_truncated: bool
    stop_index: Optional[int]  # first stop codon position in protein (0-based)
    notes: Optional[str] = None  # additional notes or warnings


# ============================================================================
# DNA Normalisation & Validation
# ============================================================================

def normalise_dna(seq: str) -> str:
    """
    Normalise DNA sequence to standard format.
    
    Removes all whitespace (spaces, tabs, newlines) and converts to uppercase.
    Essential preprocessing step to ensure consistent handling of sequences
    from different sources (FASTA files, databases, user input).
    
    Args:
        seq: Raw DNA sequence string (may contain whitespace, mixed case).
    
    Returns:
        str: Normalised sequence (uppercase, no whitespace).
    
    Example:
        >>> normalise_dna(" atg  cga\n taa ")
        'ATGCGATAA'
    """
    return "".join(seq.split()).upper()

def contains_ambiguous_bases(dna: str) -> bool:
    """
    Checks if DNA sequence contains ambiguous bases.
    
    Detects any non-ACGT bases, which typically indicate low-confidence
    regions in assembled sequences or degenerate primers. Useful for
    flagging sequences that may produce unreliable translation results.
    
    Args:
        dna: DNA sequence to check (will be normalised automatically).
    
    Returns:
        bool: True if any ambiguous bases found, False if all bases are ACGT.
    
    Example:
        >>> contains_ambiguous_bases("ATGCNA")  # N = any base
        True
        >>> contains_ambiguous_bases("ATGCGA")
        False
    """
    dna = normalise_dna(dna)
    return any(base not in VALID_DNA for base in dna)

def reverse_complement_dna(dna: str) -> str:
    """
    Compute reverse complement of DNA sequence.
    
    Essential for processing genes encoded on the minus strand, as DNA
    sequences are conventionally read 5' to 3' on the plus strand.
    
    Args:
        dna: DNA sequence (will be normalised automatically).
    
    Returns:
        str: Reverse complement (A↔T, C↔G, reversed).
    
    Example:
        >>> reverse_complement_dna("ATGC")
        'GCAT'  # complement: TACG, then reverse: GCAT
    """
    return str(Seq(normalise_dna(dna)).reverse_complement())


# ============================================================================
# Translation Functions
# ============================================================================

def translate_dna(
        dna: str,
        *,
        table: int = 11,
        to_stop: bool = False,
    ) -> str:
    """
    Translate DNA sequence to protein.
    
    Lightweight wrapper around Biopython's Seq.translate with automatic
    normalisation. Use this for simple translation without QC checks.
    For comprehensive quality control, use translate_cds_with_qc() instead.
    
    Args:
        dna: DNA sequence to translate (will be normalised automatically).
        table: NCBI genetic code table number (default: 11 = bacterial).
               See: https://www.ncbi.nlm.nih.gov/Taxonomy/Utils/wprintgc.cgi
        to_stop: If True, stop translation at first stop codon (default: False).
    
    Returns:
        str: Translated protein sequence (single-letter amino acid codes).
    
    Example:
        >>> translate_dna("ATGAAATAG", table=11, to_stop=True)
        'MK'  # stops at TAG (stop codon)
    """
    dna = normalise_dna(dna)
    return str(Seq(dna).translate(table=table, to_stop=to_stop))


def translate_cds_with_qc(
        cds_dna: str,
        *,
        genetic_code_table: int = 11,
        stop_policy: str = "truncate",
        min_len_nt: int = 3,
) -> Tuple[Optional[str], TranslationQC]:
    """
    Translate CDS to protein with comprehensive quality control.
    
    Performs translation with extensive QC checks including frameshift detection,
    ambiguous base flagging, and stop codon handling. Returns both the translated
    protein (if successful) and detailed QC metrics.
    
    Stop codon handling policies:
        - "truncate": Stop at first stop codon (standard protein translation)
        - "keep_stops": Include stop codons (*) in output (useful for mutation analysis)
    
    QC checks performed:
        1. Minimum length validation (rejects sequences < min_len_nt)
        2. Frameshift detection (length % 3 ≠ 0)
        3. Ambiguous base detection (non-ACGT characters)
        4. Stop codon detection and position tracking
        5. Translation error handling
    
    Args:
        cds_dna: Coding DNA sequence to translate.
        genetic_code_table: NCBI genetic code table (default: 11 = bacterial).
        stop_policy: How to handle stop codons ("truncate" or "keep_stops").
        min_len_nt: Minimum sequence length in nucleotides (default: 3 = 1 codon).
    
    Returns:
        Tuple containing:
            - Optional[str]: Translated protein (None if translation failed)
            - TranslationQC: Comprehensive quality control metrics
    
    Raises:
        ValueError: If stop_policy is not "truncate" or "keep_stops".
    
    Example:
        >>> protein, qc = translate_cds_with_qc("ATGAAATAG", stop_policy="truncate")
        >>> protein
        'MK'
        >>> qc.has_stop_codon
        True
        >>> qc.is_truncated
        True
    """

    if stop_policy not in {"truncate", "keep_stops"}:
        raise ValueError("stop_policy must be 'truncate' or 'keep_stops'")

    dna = normalise_dna(cds_dna)
    notes = []

    # Reject sequences that are too short to encode even a single codon
    if len(dna) < min_len_nt:
        qc = TranslationQC(
            normalised_len=len(dna),
            has_ambiguous_bases=False,
            has_stop_codon=False,
            has_frameshift=(len(dna) % 3 != 0),
            is_truncated=False,
            stop_index=None,
            notes="Sequence too short to translate"
        )
        return None, qc

    
    has_ambiguous = bool(set(dna) - VALID_DNA)
    has_frameshift = (len(dna) % 3 != 0)

    if has_frameshift:
        notes.append("CDS length not divisible by 3.")

    # Translates first without truncation to detect internal stop codons consistently.
    try: 
        full_translation = str(
            Seq(dna).translate(table=genetic_code_table, to_stop=False)
        )
    except Exception as e:
            qc = TranslationQC(
            normalised_len=len(dna),
            has_ambiguous_bases=has_ambiguous,
            has_stop_codon=False,
            has_frameshift=has_frameshift,
            is_truncated=False,
            stop_index=None,
            notes=f"Translation failed: {type(e).__name__}: {e}"
        ) 
        return None, qc
    
    stop_index = full_translation.find("*")
    has_stop = (stop_index != -1)

    if stop_policy == "truncate":
        protein = full_translation.split("*")[0]
        is_truncated = has_stop
    else:
       protein = full_translation
       is_truncated = False

    qc = TranslationQC(
        normalised_len=len(dna),
        has_ambiguous_bases=has_ambiguous,
        has_frameshift=has_frameshift,
        has_stop_codon=has_stop,
        is_truncated=is_truncated,
        stop_index=(stop_index if has_stop else None),
        notes="; ".join(notes) if notes else None,
    )

    return protein, qc


# ============================================================================
# Circular DNA Operations
# ============================================================================

def circular_slice(dna: str, start_0based: int, end_0based_excl: int) -> str:
    """
    Extract subsequence from circular DNA (e.g., plasmid).
    
    Handles wrap-around coordinates for genes spanning the plasmid origin.
    Uses Python-style 0-based indexing with exclusive end coordinate.
    
    Coordinate interpretation:
        - start < end: Normal linear slice [start:end)
        - start > end: Wrap-around slice [start:] + [:end)
        - start == end: Empty string (ambiguous - could mean empty or full circle)
    
    Args:
        dna: Circular DNA sequence (will be normalized automatically).
        start_0based: Start position (0-based inclusive).
        end_0based_excl: End position (0-based exclusive).
    
    Returns:
        str: Extracted subsequence.
    
    Raises:
        ValueError: If coordinates are negative.
    
    Example:
        >>> plasmid = "ATGCGATACG"  # Length 10
        >>> circular_slice(plasmid, 0, 3)
        'ATG'  # Normal slice
        >>> circular_slice(plasmid, 8, 2)
        'CGAT'  # Wraps around: positions 8-9 + 0-1
    """
    
    if start_0based < 0 or end_0based_excl < 0:
        raise ValueError("Coordinates must be non-negative.")

    dna = normalise_dna(dna)
    n = len(dna)
    if n == 0:
        return ""
    
    start = start_0based % n
    end = end_0based_excl % n

    if start < end:
        return dna[start:end]
    if start > end:
        # Wrap-around: take from start to end of sequence, then from beginning to end
        return dna[start:] + dna[:end]
    
    # start == end: ambiguous (could be empty or full circle)
    # Return empty string; caller must handle full-circle case if needed
    return ""
