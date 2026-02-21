"""
DNA/protein sequence utility functions for bioinformatics workflows.

This module provides foundational sequence manipulation and quality control
functions used throughout the sequence processing pipeline:

1. DNA Normalisation: Standardises input sequences (whitespace removal, uppercase)
2. Translation: DNA to protein with configurable genetic code and stop codon handling
3. Quality Control: Detects ambiguous bases, frameshifts, premature stops
4. Strand Operations: Reverse complements for minus-strand genes
5. Circular DNA: Handles genes spanning plasmid origin (wrap-around coordinates)

Key Functions:
    - translate_dna(): Simple DNA→protein translation (Biopython wrapper)
    - translate_cds_with_qc(): Translation with comprehensive QC checks
    - circular_slice(): Extracts subsequences from circular plasmids
    - normalise_dna(): Equalises the DNA input format

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


VALID_DNA: Set[str] = {"A", "C", "G", "T"}
AMBIGUOUS_BASES: Set[str] = set("NRYWSKMBDHV")

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
    stop_index: Optional[int]
    notes: Optional[str] = None


def normalise_dna(seq: str) -> str:
    """
    Normalise DNA sequence to standard format.
    
    Removes all whitespace (spaces, tabs, newlines) and converts sequence to uppercase.
    This is an essential preprocessing step to ensure consistent handling of sequences
    from different sources (FASTA files, databases, user input).
    
    Args:
        seq: Raw DNA sequence string (may contain whitespace, mixed case).
    
    Returns:
        str: Normalised sequence (uppercase, no whitespace).
    
    """
    return "".join(seq.split()).upper()

def contains_ambiguous_bases(dna: str) -> bool:
    """
    Checks if DNA sequence contains ambiguous bases by detecting any non-ACGT   
    bases,which typically indicate low-confidence regions in assembled sequences 
    or degenerate primers. This is useful for flagging sequences that may produce
    unreliable translation results.
    
    Args:
        dna: DNA sequence to check (will be normalised automatically).
    
    Returns:
        bool: True if any ambiguous bases found, False if all bases are ACGT.
    """
    dna = normalise_dna(dna)
    return any(base not in VALID_DNA for base in dna)

def reverse_complement_dna(dna: str) -> str:
    """
    Computes the reverse complement of DNA sequence. This is 
    essential for processing genes encoded on the minus strand, as DNA
    sequences are conventionally read 5' to 3' on the plus strand.
    
    Args:
        dna: DNA sequence (will be normalised automatically).
    
    Returns:
        str: Reverse complement (A↔T, C↔G, reversed).
    """
    return str(Seq(normalise_dna(dna)).reverse_complement())


def translate_dna(
        dna: str,
        *,
        table: int = 11,
        to_stop: bool = False,
    ) -> str:
    """
    Translates DNA sequence into protein using Biopython's 
    Seq.translate with automatic normalisation to ensure 
    consistent input format. 
    
    Args:
        dna: DNA sequence to translate (will be normalised automatically).
        table: NCBI genetic code table number (default: 11 = bacterial).
        to_stop: If True, stop translation at first stop codon (default: False).
    
    Returns:
        str: Translated protein sequence (single-letter amino acid codes).
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
    Translates CDS to protein with comprehensive quality control which consists of 
    frameshift detection,ambiguous base flagging, and stop codon handling. 
    Returns both the translated protein (if successful) and detailed QC metrics.
    
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
    
    """

    if stop_policy not in {"truncate", "keep_stops"}:
        raise ValueError("stop_policy must be 'truncate' or 'keep_stops'")

    dna = normalise_dna(cds_dna)
    notes = []

    # Rejects sequences that are too short to encode even a single codon
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


def reverse_complement(dna: str) -> str:
    """Backward-compatible alias for reverse complement."""
    return reverse_complement_dna(dna)

def circular_slice(dna: str, start_0based: int, end_0based_excl: int) -> str:
    """
    Extracts the subsequence from plasmid DNA by handling wrap-around coordinates.
    To achieve this, Python-style 0-based indexing with exclusive end coordinate is used.
    
    Coordinate interpretation:
        - start < end: Normal linear slice [start:end)
        - start > end: Wrap-around slice [start:] + [:end)
        - start == end: Empty string (ambiguous - could mean empty or full circle)
    
    Args:
        dna: Circular DNA sequence (will be normalised automatically).
        start_0based: Start position (0-based inclusive).
        end_0based_excl: End position (0-based exclusive).
    
    Returns:
        str: Extracted subsequence.
    
    Raises:
        ValueError: If coordinates are negative.
    
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
    
    # Return empty string; caller must handle full-circle case if needed
    return ""

