from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Set, Tuple
from Bio.Seq import Seq

# Unambiguous DNA bases used for strict QC checks.
VALID_DNA: Set[str] = {"A", "C", "G", "T"}

# Common IUPAC ambiguous codes produced by assemblers
AMBIGUOUS_BASES: Set[str] = set("NRYWSKMBDHV")

@dataclass(frozen=True)
class TranslationQC:
    """
    Quality control summary for an in-silico translation.
    Stored per variant to support downstream filtering and reporting.
    """
    normalised_len: int
    has_ambiguous_bases: bool
    has_stop_codon: bool    
    has_frameshift: bool
    is_truncated: bool
    stop_index: Optional[int]  # first stop codon position in protein (0-based)
    notes: Optional[str]=None  # additional notes or warnings

def normalise_dna(seq: str) -> str:
    """
    Normalise DNA input by removing whitespace and applying uppercase.
    This prevents subtle differences between FASTA/TSV inputs from altering results.
    """
    return "".join(seq.split()).upper()

def contains_ambiguous_bases(dna: str) -> bool:
    """
    Activates when DNA consists of any non-ACGT bases, used to flag low-confidence bases in assembled sequences.
    """
    dna = normalise_dna(dna)
    return any(base not in VALID_DNA for base in dna)

def reverse_complement_dna(dna: str) -> str:
    """
    Returns the reverse complement of a DNA sequence.
    This essential for handling genes encoded on the reverse strand.
    """
    return str(Seq(normalise_dna(dna)).reverse_complement())

def translate_dna(
        dna:str,
        *,
        table: int = 11,
        to_stop: bool = False,
    ) -> str:
    """
    Lightweight wrapper around Biopython's Seq.translate with built-in normalisation.
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
    Translates a coding DNA sequence (CDS) into a protein while performing structured QC checks.
    
    stop_policy controls how internal stop codons are handled:
    - "truncate": translation stops at the first stop codon, producing a truncated protein.
    - "keep_stops": translation continues through stop codons, keeping them in the protein sequence.
    """

    if stop_policy not in {"truncate", "keep_stops"}:
        raise ValueError("stop_policy must be 'truncate' or 'keep_stops'")

    # Normalisation ensures all downstream checks are consistent
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
        # Translation can fail for badly malformed sequences 
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



def circular_slice(dna: str, start_0based: int, end_0based_excl: int) -> str:
    """
   Takes out a subsequence from circular DNA using 0-based coordinates. 

   Deals with wrap-around when the end position is before the start position.

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
        return dna[start:] + dna[:end]
    
    # start == end means a full circle, but to avoid ambiguity we return an empty string and rely on the caller to check the length if they want to interpret it as a full circle.
    return ""
