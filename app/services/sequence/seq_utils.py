from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Set
from Bio.Seq import Seq

# Valid unambiguous DNA bases
VALID_DNA: Set[str] = {"A", "C", "G", "T"}

# Common IUPAC ambiguous codes produced by assemblers
IUPAC_AMBIGUOUS: Set[str] = set("NRYWSKMBDHV")

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
    Organises DNA input by removing whitespace and applying uppercase.
    Ensures consistent behaviour across uploaded FASTA / TSV sources.
    """
    return "".join(seq.split()).upper()

def translate_cds_with_qc(
        cds_dna:str,
        *,
        genetic_code_table: int = 11,
        stop_policy: str = "truncate",   # "truncate" or "keep_stops"
        min_len_nt: int = 3,
    ) -> tuple[Optional[str], TranslationQC]:
    """
    Translates a coding DNA sequence (CDS) into a protein while performing QC checks.
    
    This function is purposefully self-contained so it can be:
    1) unit tested without Flask or the database
    2) reused for WT and variant sequences 
    3) called inside background jobs
    
    Returns:
        (protein_sequence | None, TranslationQC)
    """

    # Normalisation ensures all downstream checks are consistent
    dna = normalise_dna(cds_dna)
    notes = None

    # Reject sequences that too short to encode even a single codon
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

    # Any base outside A,C,G,T is treated as ambiguous for QC purposes
    # although Biopython may still translate them to 'X'
    has_ambiguous = any(base not in VALID_DNA for base in dna)

    # Frameshifts break codon alignment and usually invalidate translation
    has_frameshift = (len(dna) % 3 != 0)
    if has_frameshift:
        notes = "CDS length not divisible by 3 (from frameshift or incomplete assembly)."

    # Translation policy:
    # - "truncate": stop translation at first stop codon
    # - "keep_stops": retain stop codons as '*' in protein sequence

    try: 
        protein = str(
            Seq(dna).translate(table=genetic_code_table, to_stop=(stop_policy=="truncate"))
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

    # Stop codon detection differs depending on translation policy
    if stop_policy == "keep_stops":
        stop_index = protein.find("*")
        has_stop = (stop_index != -1)
        is_truncated = False
    else:
        # when trucating, stops are removed - so we detect them by translating
        # without truncation and checking for '*'
        full_translation = str(
            Seq(dna).translate(
                table=genetic_code_table, 
                to_stop=False
                )
        )
        stop_index = full_translation.find("*")
        has_stop = (stop_index != -1)
        is_truncated = has_stop

    qc = TranslationQC(
        normalised_len=len(dna),
        has_ambiguous_bases=has_ambiguous,
        has_frameshift=has_frameshift,
        has_stop_codon=has_stop,
        is_truncated=is_truncated,
        stop_index=(stop_index if has_stop else None),
        notes=notes,
    )

    return protein, qc

def reverse_complement_dna(dna: str) -> str:
    """
    Returns the reverse complement of a DNA sequence.

    This function is required for handling genes encoded on the reverse
    stand of circular plasmids.
    """
    dna = normalise_dna(dna)
    return str(Seq(dna).reverse_complement())

def reverse_complement(dna: str) -> str:
    """Backward-compatible alias for reverse complement."""
    return reverse_complement_dna(dna)

def contains_ambiguous_bases(dna: str) -> bool:
    """Return True if sequence contains non-ACGT bases."""
    dna = normalise_dna(dna)
    return any(base not in VALID_DNA for base in dna)

def translate_dna(dna: str, *, table: int = 11, to_stop: bool = True) -> str:
    """Translate DNA to protein using Biopython."""
    dna = normalise_dna(dna)
    return str(Seq(dna).translate(table=table, to_stop=to_stop))

def circular_slice(dna: str, start_0based: int, end_0based_excl: int) -> str:
    """
   Extracts a subsequence from circular DNA using 0-based coordinates. 

   Deals with wrap-around when the end position is before the start position.
   e.g. circular_slice("ACGTACGT", 6, 2) -> "GTAC"
   """
    dna = normalise_dna(dna)
    n = len(dna)

    if n == 0:
        return ""
    
    start = start_0based % n
    end = end_0based_excl % n

    if start < end:
        return dna[start:end]
    elif start > end:
        # Wrap-around case
        return dna[start:] + dna[:end]
    else:
        # start == end implies empty slice in CDS context 
        return ""
