"""
Sequence Processing Service for Variant Analysis.

This module provides core functionality for processing DNA sequences in directed evolution
experiments, including:
    - Wild-type (WT) gene identification in circular plasmids via 6-frame alignment
    - Variant CDS extraction and translation with quality control
    - Mutation calling (synonymous, nonsynonymous, indels, frameshifts)
    - Protein alignment-based indel detection

The pipeline follows a reference-guided approach where the WT protein sequence from UniProt
is aligned against all 6 reading frames of the plasmid to identify the correct CDS coordinates,
which are then used to process all variant sequences consistently.

Key Classes:
    WTMapping: Captures WT gene mapping results (coordinates, strand, frame)
    VariantSeqResult: Stores per-variant CDS and translation results with QC flags
    MutationRecord: Represents individual mutations with classification
    MutationCounts: Aggregated mutation statistics

Algorithm Overview:
    1. WT mapping: 6-frame translation + BLOSUM62 alignment → CDS coordinates
    2. Variant processing: Extract CDS using WT coords → translate → QC
    3. Mutation calling: Codon-by-codon comparison or protein alignment for indels
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import List, Tuple, Optional

from Bio.Align import PairwiseAligner
from Bio.Align import substitution_matrices
from Bio import BiopythonWarning

from app.config import settings
from app.utils.seq_utils import (
    normalise_dna,
    reverse_complement_dna,
    circular_slice,
    contains_ambiguous_bases,
    translate_dna,
)


# ============================================================================
# Data Models
# ============================================================================

@dataclass(frozen=True)
class WTMapping:
    """
    Wild-type gene mapping result capturing CDS location in plasmid.
    
    Attributes:
        strand: Coding strand, either "PLUS" or "MINUS".
        frame: Reading frame offset (0, 1, or 2).
        cds_start_0based: Start position of CDS in plasmid (0-based, inclusive).
        cds_end_0based_excl: End position of CDS in plasmid (0-based, exclusive).
        wt_cds_dna: Extracted wild-type CDS sequence in coding orientation.
        wt_protein_aa: Wild-type protein sequence.
        match_identity_pct: Percent identity between aligned WT protein and translated CDS.
        alignment_score: BLOSUM62 alignment score.
    """
    strand: str
    frame: int
    cds_start_0based: int
    cds_end_0based_excl: int
    wt_cds_dna: str
    wt_protein_aa: str
    match_identity_pct: float
    alignment_score: float


@dataclass(frozen=True)
class QCFlags:
    """
    Quality control flags for translated sequences.
    
    Attributes:
        has_ambiguous_bases: True if CDS contains non-ACGT bases (N, R, Y, etc.).
        has_frameshift: True if CDS length is not divisible by 3.
        has_premature_stop: True if stop codon found before expected end.
        notes: Additional QC information or error messages.
    """
    has_ambiguous_bases: bool
    has_frameshift: bool
    has_premature_stop: bool
    notes: Optional[str] = None


@dataclass(frozen=True)
class VariantSeqResult:
    """
    Variant sequence processing result including CDS and QC status.
    
    Attributes:
        cds_start_0based: CDS start position (0-based, may be None if extraction failed).
        cds_end_0based_excl: CDS end position (0-based exclusive).
        strand: Coding strand ("PLUS" or "MINUS").
        frame: Reading frame (0, 1, or 2).
        cds_dna: Extracted CDS sequence (None if extraction failed).
        protein_aa: Translated protein sequence (None if translation failed).
        qc: Quality control flags and notes.
    """
    cds_start_0based: Optional[int]
    cds_end_0based_excl: Optional[int]
    strand: Optional[str]
    frame: Optional[int]
    cds_dna: Optional[str]
    protein_aa: Optional[str]
    qc: QCFlags


@dataclass(frozen=True)
class MutationRecord:
    """
    Single mutation record with classification and coordinates.
    
    Attributes:
        mutation_type: Classification - SYNONYMOUS, NONSYNONYMOUS, NONSENSE, 
                       FRAMESHIFT, INSERTION, DELETION, or AMBIGUOUS.
        codon_index_1based: 1-based codon position in CDS.
        aa_position_1based: 1-based amino acid position in protein.
        wt_codon: Wild-type codon (None for deletions/frameshifts).
        var_codon: Variant codon (None for deletions/frameshifts).
        wt_aa: Wild-type amino acid (None for deletions/frameshifts).
        var_aa: Variant amino acid (None for deletions/frameshifts).
        notes: Additional context about the mutation.
    """
    mutation_type: str
    codon_index_1based: Optional[int]
    aa_position_1based: Optional[int]
    wt_codon: Optional[str]
    var_codon: Optional[str]
    wt_aa: Optional[str]
    var_aa: Optional[str]
    notes: Optional[str] = None


@dataclass(frozen=True)
class MutationCounts:
    """
    Aggregated mutation statistics for a variant.
    
    Attributes:
        synonymous: Count of synonymous (silent) mutations.
        nonsynonymous: Count of nonsynonymous mutations (including nonsense).
        total: Total mutation count.
    """
    synonymous: int
    nonsynonymous: int
    total: int


# ============================================================================
# Alignment Utilities
# ============================================================================
# Pre-load BLOSUM62 once at import time so it is not re-read from disk
# on every alignment call (substitution_matrices.load is I/O-bound).
_BLOSUM62 = substitution_matrices.load("BLOSUM62")


def _make_protein_aligner(mode: str = "global") -> PairwiseAligner:
    """
    Configures a pairwise aligner with BLOSUM62 and gap penalties.
    
    Uses the module-level cached BLOSUM62 matrix to avoid reloading
    from disk on every call.
    
    Args:
        mode: Alignment mode - "global" or "local".
    
    Returns:
        PairwiseAligner: Configured with BLOSUM62 scoring.
    """
    aligner = PairwiseAligner()
    aligner.mode = mode
    aligner.substitution_matrix = _BLOSUM62
    aligner.open_gap_score = -10.0
    aligner.extend_gap_score = -0.5
    return aligner


# Cached aligners for reuse across calls (PairwiseAligner is stateless
# after configuration, so sharing instances is safe).
_GLOBAL_ALIGNER = _make_protein_aligner("global")
_LOCAL_ALIGNER = _make_protein_aligner("local")

def _identity_pct_from_alignment(aln) -> float:
    """
    Calculates percent identity from a Biopython alignment object.
    Utilises Biopython's aligned coordinate blocks to compute identity over
    aligned regions, ignoring any gaps in either sequence.
    
    Args:
        aln: Biopython alignment object with .sequences and .aligned attributes.
    
    Returns:
        float: Percent identity (0.0 to 100.0) considering only aligned positions.
    """
    query = aln.sequences[0]
    target = aln.sequences[1]
    q_spans = aln.aligned[0]
    t_spans = aln.aligned[1]

    matches = 0 
    aligned_cols = 0

    for (q0, q1), (t0, t1) in zip(q_spans, t_spans):
        seg_len = min(q1 - q0, t1 - t0)
        if seg_len <= 0:
            continue
        aligned_cols += seg_len
        q_seg = query[q0:q0 + seg_len]
        t_seg = target[t0:t0 + seg_len]
        matches += sum (1 for i in range(seg_len) if q_seg[i] == t_seg[i])
        
    return (matches / aligned_cols * 100.0) if aligned_cols else 0.0


# ============================================================================
# Translation & Sequence Utilities
# ============================================================================

def _gapped_seqs_from_alignment(aln) -> Tuple[str, str]:
    """
    Reconstruct gapped alignment strings from structured coordinate blocks.

    Uses Biopython's aln.aligned arrays instead of the human-readable
    aln.format() output, which is fragile across Biopython versions and
    breaks on line-wrapped or annotated output.

    Args:
        aln: Biopython PairwiseAlignment object.

    Returns:
        Tuple of (gapped_seq_a, gapped_seq_b) with '-' for gap characters.
    """
    seq_a = str(aln.sequences[0])
    seq_b = str(aln.sequences[1])
    blocks_a = aln.aligned[0]
    blocks_b = aln.aligned[1]

    if len(blocks_a) == 0:
        return "", ""

    gapped_a: list[str] = []
    gapped_b: list[str] = []

    prev_a_end = int(blocks_a[0][0])
    prev_b_end = int(blocks_b[0][0])

    # Leading unaligned residues (global alignment may have leading gaps)
    if prev_a_end > 0 and prev_b_end == 0:
        gapped_a.append(seq_a[:prev_a_end])
        gapped_b.append("-" * prev_a_end)
    elif prev_b_end > 0 and prev_a_end == 0:
        gapped_a.append("-" * prev_b_end)
        gapped_b.append(seq_b[:prev_b_end])
    elif prev_a_end > 0 and prev_b_end > 0:
        # Both have leading unaligned - treat longer as gapping the shorter
        gapped_a.append(seq_a[:prev_a_end])
        gapped_b.append(seq_b[:prev_b_end])

    for idx in range(len(blocks_a)):
        a_start, a_end = int(blocks_a[idx][0]), int(blocks_a[idx][1])
        b_start, b_end = int(blocks_b[idx][0]), int(blocks_b[idx][1])

        if idx > 0:
            gap_a = a_start - prev_a_end  # unaligned residues in A
            gap_b = b_start - prev_b_end  # unaligned residues in B
            if gap_a > 0:
                gapped_a.append(seq_a[prev_a_end:a_start])
                gapped_b.append("-" * gap_a)
            if gap_b > 0:
                gapped_b.append(seq_b[prev_b_end:b_start])
                gapped_a.append("-" * gap_b)

        # Aligned block (same length in both sequences)
        gapped_a.append(seq_a[a_start:a_end])
        gapped_b.append(seq_b[b_start:b_end])

        prev_a_end = a_end
        prev_b_end = b_end

    # Trailing unaligned residues
    if prev_a_end < len(seq_a):
        tail = len(seq_a) - prev_a_end
        gapped_a.append(seq_a[prev_a_end:])
        gapped_b.append("-" * tail)
    if prev_b_end < len(seq_b):
        tail = len(seq_b) - prev_b_end
        gapped_b.append(seq_b[prev_b_end:])
        gapped_a.append("-" * tail)

    return "".join(gapped_a), "".join(gapped_b)


def _safe_codon(dna: str, codon_index_1based: Optional[int]) -> Optional[str]:
    """
    Extracts codon from DNA sequence at specified 1-based position.
    
    Args:
        dna: DNA sequence string.
        codon_index_1based: 1-based codon position (e.g., 1 for first codon).
    
    Returns:
        Optional[str]: 3-nucleotide codon, or None if position invalid or 
                       insufficient sequence length.
    """
    if codon_index_1based is None:
        return None
    i0 = (codon_index_1based - 1) * 3
    i1 = i0 + 3
    if i1 > len(dna):
        return None
    return dna[i0:i1]


# ============================================================================
# Main Sequence Processing Functions
# ============================================================================

def map_wt_gene_in_plasmid(wt_protein_aa: str, wt_plasmid_dna: str) -> WTMapping:
    """
    Locates the wild-type CDS within circular plasmid using 6-frame protein alignment.
    
    Performs an exhaustive 6-frame translation search (3 frames x 2 strands) on a
    circularised plasmid sequence, aligning each translated frame against the
    reference protein using BLOSUM62. Returns the best-scoring mapping that
    exceeds the minimum identity threshold.
    
    Algorithm:
        1. Circularise plasmid by concatenating (handles genes spanning origin)
        2. For each strand (PLUS, MINUS):
            a. On each frame (0, 1, 2):
                - Translate to protein
                - Global align vs reference protein
                - Calculate percent identity
                - If identity ≥ WT_MIN_IDENTITY_PCT, validate candidate
        3. Return candidate with the highest identity (ties broken by score)
    
    Validation checks:
        - Identity must meet WT_MIN_IDENTITY_PCT threshold (config)
        - CDS length must be multiple of 3
        - No ambiguous bases (N, R, Y, etc.)
        - Translated protein ≥ 80% of reference length (tolerance for truncation)
    
    Args:
        wt_protein_aa: Reference protein sequence (amino acids).
        wt_plasmid_dna: Circular plasmid DNA sequence.
    
    Returns:
        WTMapping: Best mapping with strand, frame, coordinates, sequences, 
                   identity percentage, and alignment score.
    
    Raises:
        ValueError: If plasmid or protein is empty.
        RuntimeError: If no valid mapping found above identity threshold.
    
    Note:
        The 0.8 length threshold (80%) allows flexibility for minor truncations
        or annotation differences while rejecting short spurious matches.
    """
    wt_protein = wt_protein_aa.strip().upper()
    plasmid = normalise_dna(wt_plasmid_dna)

    if not plasmid:
        raise ValueError("WT plasmid sequence is empty.")
    if not wt_protein:
        raise ValueError("WT protein reference is empty.")
    
    n = len(plasmid) 
    circular = plasmid + plasmid

    aligner = _LOCAL_ALIGNER

    best:Optional[WTMapping] = None
    best_score = float("-inf")
    best_identity = float("-inf")

    strands = {
        "PLUS": circular,
        "MINUS": reverse_complement_dna(circular),
    }

    for strand_name, seq in strands.items():
        for frame in (0, 1, 2):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", BiopythonWarning)
                translated = translate_dna(
                    seq[frame:],
                    table=settings.GENETIC_CODE_TABLE,
                    to_stop=False,
                )
            if not translated:
                continue

            aln = aligner.align(translated, wt_protein_aa)[0]
            score = float(aln.score)
            identity_pct = _identity_pct_from_alignment(aln)

            if identity_pct < settings.WT_MIN_IDENTITY_PCT:
                continue
            
            # First aligned query amino acid position secures nucleotide start 
            if aln.aligned[0].size == 0 or aln.aligned[0][0].size == 0:
                continue

            q0_prot = int(aln.aligned[0][0][0])
            t0_prot = int(aln.aligned[1][0][0])

            # Adjust CDS start to account for any leading WT residues
            # before the alignment anchor (t0_prot > 0 means the alignment
            # matched starting partway into the WT protein).
            nt_start = frame + (q0_prot - t0_prot) * 3
            nt_end = nt_start + (len(wt_protein) * 3)

            # Clamp to valid range within the doubled-plasmid coordinate space
            max_nt = 2 * n
            if nt_start < 0 or nt_end > max_nt:
                continue

            nt_start_mod = nt_start % n
            nt_end_mod = nt_end % n

            # Edge case: CDS spans the entire plasmid (end wraps to start)
            if nt_end_mod == nt_start_mod and (nt_end - nt_start) == n:
                wt_cds = plasmid[nt_start_mod:] + plasmid[:nt_start_mod] if nt_start_mod != 0 else plasmid
            else:
                wt_cds = circular_slice(
                    plasmid,
                    nt_start_mod,
                    nt_end_mod,
                )

            # Always returns CDS in coding orientation
            if strand_name == "MINUS":
                wt_cds = reverse_complement_dna(wt_cds)

            if len(wt_cds) < 3 or (len(wt_cds) % 3 != 0):
                continue
            if contains_ambiguous_bases(wt_cds):
                continue

            wt_cds_prot = translate_dna(
                wt_cds,
                table=settings.GENETIC_CODE_TABLE,
                to_stop=False,
            )
            if not wt_cds_prot:
                continue

            if len(wt_cds_prot) < max(1, int(0.8 * len(wt_protein))):
                continue

            candidate = WTMapping(
                strand=strand_name,
                frame=frame,
                cds_start_0based=nt_start_mod,
                cds_end_0based_excl=nt_end_mod,
                wt_cds_dna=wt_cds,
                wt_protein_aa=wt_protein,
                match_identity_pct=identity_pct,
                alignment_score=score,
            )

            if (identity_pct > best_identity) or (
                identity_pct == best_identity and score > best_score):
                best = candidate
                best_identity = identity_pct
                best_score = score

    if best is None:
        raise RuntimeError(
            "Unable to locate WT CDS in plasmid above identity threshold."
        )
    return best


# Variant processing

def process_variant_plasmid(
        variant_plasmid_dna: str,
        wt_mapping: WTMapping,
        *,
        fallback_search: bool,
) -> VariantSeqResult:
    """
    Uses the WT mapping (strand, frame, coordinates) to extract the corresponding
    CDS from the variant plasmid, translate it, and perform quality control checks.
    
    Process:
        1. Extracts CDS using circular_slice (handles wrap-around coordinates)
        2. Applies strand orientation (reverse complement if MINUS strand)
        3. Translates to protein using configured genetic code
        4. Performs QC checks (frameshifts, ambiguous bases, premature stops)
    
    Note on reading frame:
        The frame offset is already incorporated into cds_start_0based /
        cds_end_0based_excl during WT mapping, so no trimming is done here.
    
    Args:
        variant_plasmid_dna: Variant plasmid DNA sequence.
        wt_mapping: Wild-type mapping with coordinates and orientation.
        fallback_search: If True and extraction fails, this performs a de novo search
                        (currently placeholder - not yet implemented).
    
    Returns:
        VariantSeqResult: Contains extracted CDS, translated protein, coordinates,
                         and QC flags indicating any issues detected.
    
    Note:
        STOP_POLICY configuration controls stop codon handling:
        - "truncate": Stop at first stop codon, flags if the variant protein is shorter than WT
        - Other: Keep stops in sequence, flags any embedded stop codons
    """
    plasmid = normalise_dna(variant_plasmid_dna)
    n = len(plasmid)

    start = wt_mapping.cds_start_0based
    end = wt_mapping.cds_end_0based_excl

    # Handle full-circle CDS (start == end means the gene spans the entire plasmid)
    if start == end and len(wt_mapping.wt_cds_dna) >= n:
        cds_dna = plasmid[start:] + plasmid[:start] if start != 0 else plasmid
    else:
        cds_dna = circular_slice(plasmid, start, end)
    
    if wt_mapping.strand == "MINUS":
        cds_dna = reverse_complement_dna(cds_dna)

    # Frame offset is already incorporated into cds_start_0based / cds_end_0based_excl
    # during WT mapping, so no additional trimming is needed here.

    has_frameshift = (len(cds_dna) % 3 != 0)
    has_ambig = contains_ambiguous_bases(cds_dna)

    to_stop = (settings.STOP_POLICY == "truncate")

    protein: Optional[str] = None
    prem_stop = False
    notes: Optional[str] = None

    if cds_dna:
        try:
            protein = translate_dna(
                cds_dna, 
                table=settings.GENETIC_CODE_TABLE,
                to_stop=to_stop,)

            if settings.STOP_POLICY != "truncate" and protein and "*" in protein:
                prem_stop = True
                notes = "Stop codon(s) present in translated protein."

            if settings.STOP_POLICY == "truncate" and protein:
                if len(protein) < len(wt_mapping.wt_protein_aa):
                    prem_stop = True
                    notes = "Protein truncated due to in-frame stop codon."

        except Exception as e:
            protein = None
            notes = f"Translation failed: {type(e).__name__}: {e}"

    qc = QCFlags(
        has_ambiguous_bases=has_ambig,
        has_frameshift=has_frameshift,
        has_premature_stop=prem_stop,
        notes=notes,     
    )
    
    if fallback_search and (protein is None or has_frameshift):
        # repeat mapping for this variant only
        pass

    return VariantSeqResult(
        cds_start_0based=wt_mapping.cds_start_0based,
        cds_end_0based_excl=wt_mapping.cds_end_0based_excl,
        strand=wt_mapping.strand,
        frame=wt_mapping.frame,
        cds_dna=cds_dna,
        protein_aa=protein,
        qc=qc,
    )

# Mutation calling

def call_indels_via_protein_alignment(
        wt_cds_dna: str,
        var_cds_dna: str, 
) -> Tuple[List[MutationRecord], MutationCounts]:
    """
    Detects mutations using protein-level alignment (indel-aware).
    
    Translates both WT and variant CDS to protein, performs global alignment,
    then walks through aligned columns to detect insertions, deletions, and
    substitutions for a more robust approach.
    
    Algorithm:
        1. Translates both sequences to protein (keep stop codons as *)
        2. Performs global protein alignment with BLOSUM62 scoring
        3. Walks through alignment columns:
            - WT gap + variant residue → INSERTION
            - WT residue + variant gap → DELETION
            - Both residues present:
                a. Checks if amino acids match (synonymous vs nonsynonymous)
                b. Retrieves codons from DNA for classification
                c. Detects nonsense mutations (stop codon introduced)
    
    Args:
        wt_cds_dna: Wild-type CDS DNA sequence.
        var_cds_dna: Variant CDS DNA sequence.
    
    Returns:
        Tuple containing:
            - List[MutationRecord]: All detected mutations with coordinates
            - MutationCounts: Aggregated counts (synonymous, nonsynonymous, total)        
    """
    wt_cds = normalise_dna(wt_cds_dna)
    var_cds = normalise_dna(var_cds_dna)

    wt_prot = translate_dna(wt_cds, table=settings.GENETIC_CODE_TABLE, to_stop=False)
    var_prot = translate_dna(var_cds, table=settings.GENETIC_CODE_TABLE, to_stop=False)

    aln = _GLOBAL_ALIGNER.align(wt_prot, var_prot)[0]

    # Use structured coordinate blocks instead of fragile aln.format() text
    wt_aln, var_aln = _gapped_seqs_from_alignment(aln)
    if not wt_aln:
        return ([], MutationCounts(synonymous=0, nonsynonymous=0, total=0))

    muts: List[MutationRecord] = []
    syn = 0
    nonsyn = 0
    total = 0

    wt_pos = 0 # 1-based AA position in WT (advanced when WT char != '-')
    var_pos = 0 # 1-based AA position in variant (advanced when variant char != '-')

    for wa, va in zip(wt_aln, var_aln):
        if wa != "-":
            wt_pos += 1
        if va != "-":
            var_pos += 1
    
        if wa == "-" and va != "-":
            total += 1
            nonsyn += 1
            muts.append(
                MutationRecord(
                    mutation_type="INSERTION",
                    codon_index_1based=var_pos,
                    aa_position_1based=var_pos,
                    wt_codon=None,
                    var_codon=_safe_codon(var_cds_dna, var_pos),
                    wt_aa=None,
                    var_aa=va,
                    notes="In-frame insertion (protein alignment).",
                )
            )
            continue

        if wa != "-" and va == "-":
            total += 1
            nonsyn += 1
            muts.append(
                MutationRecord(
                    mutation_type="DELETION",
                    codon_index_1based=wt_pos,
                    aa_position_1based=wt_pos,
                    wt_codon=_safe_codon(wt_cds_dna, wt_pos),
                    var_codon=None,
                    wt_aa=wa,
                    var_aa=None,
                    notes= "In-frame deletion (protein alignment).",
                )
            )
            continue

        if wa == va:
            continue

        total += 1

        wt_codon = _safe_codon(wt_cds_dna, wt_pos)
        var_codon = _safe_codon(var_cds_dna, var_pos)   

        if wt_codon and var_codon:
            wt_aa = translate_dna(wt_codon, table=settings.GENETIC_CODE_TABLE, to_stop=False)
            var_aa = translate_dna(var_codon, table=settings.GENETIC_CODE_TABLE, to_stop=False)

            if var_aa == "*":
                mtype = "NONSENSE"
                nonsyn += 1
            elif wt_aa == var_aa:
                mtype = "SYNONYMOUS"
                syn += 1
            else:
                mtype = "NONSYNONYMOUS"
                nonsyn += 1
        else:
            # Codon retrieval failed (e.g. near sequence ends), classify as nonsynonymous
            wt_aa = wa if wa != "-" else None
            var_aa = va if va != "-" else None
            mtype = "NONSYNONYMOUS"
            nonsyn += 1

        muts.append(
            MutationRecord(
                mutation_type=mtype,
                codon_index_1based=wt_pos,
                aa_position_1based=wt_pos,
                wt_codon=wt_codon,
                var_codon=var_codon,
                wt_aa=wt_aa if wt_codon and var_codon else (wa if wa != "-" else None),
                var_aa=var_aa if wt_codon and var_codon else (va if va != "-" else None),
                notes="Protein-alignment mismatch mapped to nearest codon." if not (wt_codon and var_codon) else None,
            )
        )

    return muts, MutationCounts(synonymous=syn, nonsynonymous=nonsyn, total=total)

    
def call_mutations_against_wt(
        wt_cds_dna: str,
        var_cds_dna: str,
) -> Tuple[List[MutationRecord], MutationCounts]:
    """
    Main mutation calling entry point with adaptive strategy selection.
    
    Determines the appropriate mutation detection algorithm based on sequence
    characteristics to optimise accuracy and performance:
    
    Strategy selection:
        1. Frameshift check: If either CDS length not divisible by 3
           → Returns single FRAMESHIFT record (detailed calling impossible)
        
        2. Length mismatch (but both in-frame): If len(WT) ≠ len(variant)
           → Delegates to protein alignment, which absorbs insertions and
             deletions into gap characters so surrounding residues stay
             correctly paired (codon-by-codon would misalign everything
             downstream of the indel)
        
        3. Equal length sequences
           → Use fast codon-by-codon comparison (most efficient)
    
    The codon-by-codon approach compares triplets directly and classifies each:
        - Identical codon → Skip (no mutation)
        - Ambiguous bases → AMBIGUOUS classification
        - Stop codon introduced → NONSENSE (nonsynonymous)
        - Amino acid remains same → SYNONYMOUS
        - Amino acid changes → NONSYNONYMOUS
    
    Args:
        wt_cds_dna: Wild-type CDS DNA sequence.
        var_cds_dna: Variant CDS DNA sequence.
    
    Returns:
        Tuple containing:
            - List[MutationRecord]: All detected mutations with full annotations
            - MutationCounts: Summary statistics (synonymous, nonsynonymous, total)
    """
    wt = normalise_dna(wt_cds_dna)
    var = normalise_dna(var_cds_dna)

    if (len(wt) % 3 != 0) or (len(var) % 3 != 0):
        return (
            [
                MutationRecord(
                    mutation_type="FRAMESHIFT",
                    codon_index_1based=None,
                    aa_position_1based=None,
                    wt_codon=None,
                    var_codon=None,
                    wt_aa=None,
                    var_aa=None,
                    notes="CDS not divisible by 3; frameshift detected.",
                )
            ],
            MutationCounts(0, 0, 1),
        )

    if len(wt) != len(var):
        return call_indels_via_protein_alignment(wt, var)

    muts: List[MutationRecord] = []
    syn = 0
    nonsyn = 0
    total = 0

    codons = len(wt) // 3
    for i in range(codons):
        wt_codon = wt[i * 3 : i * 3 + 3]
        var_codon = var[i * 3 : i * 3 + 3]

        if wt_codon == var_codon:
            continue

        total += 1

        # Ambiguous bases in the variant codon means we cannot reliably classify the mutation
        if any(b not in {"A", "T", "C", "G"} for b in var_codon):
            muts.append(
                MutationRecord(
                    mutation_type="AMBIGUOUS",
                    codon_index_1based=i + 1,
                    aa_position_1based=i + 1,
                    wt_codon=wt_codon,
                    var_codon=var_codon,
                    wt_aa=None,
                    var_aa=None,
                    notes="Ambiguous base(s) in variant codon.",
                )
            )
            continue

        wt_aa = translate_dna(wt_codon, table=settings.GENETIC_CODE_TABLE, to_stop=False)
        var_aa = translate_dna(var_codon, table=settings.GENETIC_CODE_TABLE, to_stop=False)

        if var_aa == "*":
            mtype = "NONSENSE"
            nonsyn += 1
        elif wt_aa == var_aa:
            mtype = "SYNONYMOUS"
            syn += 1
        else:
            mtype = "NONSYNONYMOUS"
            nonsyn += 1

        muts.append(
            MutationRecord(
                mutation_type=mtype,
                codon_index_1based=i + 1,
                aa_position_1based=i + 1,
                wt_codon=wt_codon,
                var_codon=var_codon,
                wt_aa=wt_aa,
                var_aa=var_aa,
                notes=None,
            )
        )

    return muts, MutationCounts(synonymous=syn, nonsynonymous=nonsyn, total=total)
