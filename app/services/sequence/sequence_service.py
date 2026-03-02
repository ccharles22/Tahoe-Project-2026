"""
Sequence Processing Service for Variant Analysis.

Core logic for WT gene mapping, variant CDS extraction, translation/QC,
and mutation calling. See the project MkDocs for detailed algorithm
documentation and visualisations.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from functools import lru_cache
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
    Reconstructs gapped alignment strings from structured coordinate blocks.

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

    # Leading unaligned residues (ensure both gapped strings stay same length)
    lead_a = prev_a_end
    lead_b = prev_b_end
    if lead_a > 0 or lead_b > 0:
        lead_len = max(lead_a, lead_b)
        gapped_a.append(seq_a[:lead_a] + "-" * (lead_len - lead_a))
        gapped_b.append(seq_b[:lead_b] + "-" * (lead_len - lead_b))

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


def _split_codons(dna: str) -> List[str]:
    """Split a CDS into complete 3-base codons."""
    return [dna[i : i + 3] for i in range(0, len(dna), 3) if i + 3 <= len(dna)]


@lru_cache(maxsize=128)
def _translate_codon_cached(codon: str) -> str:
    """Translate a single unambiguous codon, caching the tiny 64-codon space."""
    return translate_dna(codon, table=settings.GENETIC_CODE_TABLE, to_stop=False)


def _codon_similarity_score(wt_codon: str, var_codon: str) -> int:
    """
    Score a codon-vs-codon substitution for global alignment.

    The alignment is codon-aware rather than residue-aware so synonymous
    substitutions remain visible as mutation events in offset / indel cases.
    """
    if wt_codon == var_codon:
        return 4

    if any(b not in {"A", "T", "C", "G"} for b in wt_codon + var_codon):
        return 0

    wt_aa = _translate_codon_cached(wt_codon)
    var_aa = _translate_codon_cached(var_codon)

    if wt_aa == var_aa:
        return 2
    if var_aa == "*":
        return -3
    return -2


def _align_codons_global(
    wt_codons: List[str],
    var_codons: List[str],
) -> Tuple[List[Optional[str]], List[Optional[str]]]:
    """
    Global-align two codon lists using banded Needleman-Wunsch DP.

    When sequences are close in length (typical for directed evolution indels),
    a narrow diagonal band is used to reduce the DP from O(n²) to O(nxw),
    where w = 2*band+1.  For sequences with large length differences or small
    sequences the full DP is used.
    """
    gap_penalty = -1
    n = len(wt_codons)
    m = len(var_codons)

    diff = abs(n - m)
    # Use banded alignment when sequences are large and close in length
    use_band = (n > 60 or m > 60) and diff <= 20
    band = diff + 6 if use_band else max(n, m)  # generous padding around the diagonal

    NEG_INF = float("-inf")

    score = [[NEG_INF] * (m + 1) for _ in range(n + 1)]
    trace = [[""] * (m + 1) for _ in range(n + 1)]
    score[0][0] = 0

    for i in range(1, n + 1):
        if i <= band:
            score[i][0] = score[i - 1][0] + gap_penalty
            trace[i][0] = "U"
    for j in range(1, m + 1):
        if j <= band:
            score[0][j] = score[0][j - 1] + gap_penalty
            trace[0][j] = "L"

    for i in range(1, n + 1):
        wt_codon = wt_codons[i - 1]
        # Diagonal is at j = i * m/n (approximately i when n≈m)
        # For banded: restrict j to [diag - band, diag + band]
        diag_j = round(i * m / n) if n > 0 else i
        j_lo = max(1, diag_j - band)
        j_hi = min(m, diag_j + band)
        for j in range(j_lo, j_hi + 1):
            var_codon = var_codons[j - 1]
            diag = score[i - 1][j - 1]
            if diag > NEG_INF:
                diag += _codon_similarity_score(wt_codon, var_codon)
            up = score[i - 1][j]
            if up > NEG_INF:
                up += gap_penalty
            left = score[i][j - 1]
            if left > NEG_INF:
                left += gap_penalty

            best = diag
            move = "D"
            if up > best:
                best = up
                move = "U"
            if left > best:
                best = left
                move = "L"

            score[i][j] = best
            trace[i][j] = move

    aligned_wt: List[Optional[str]] = []
    aligned_var: List[Optional[str]] = []
    i = n
    j = m

    while i > 0 or j > 0:
        move = trace[i][j] if i >= 0 and j >= 0 else ""
        if i > 0 and j > 0 and move == "D":
            aligned_wt.append(wt_codons[i - 1])
            aligned_var.append(var_codons[j - 1])
            i -= 1
            j -= 1
        elif i > 0 and (j == 0 or move == "U"):
            aligned_wt.append(wt_codons[i - 1])
            aligned_var.append(None)
            i -= 1
        else:
            aligned_wt.append(None)
            aligned_var.append(var_codons[j - 1])
            j -= 1

    aligned_wt.reverse()
    aligned_var.reverse()
    return aligned_wt, aligned_var


def _prefer_codon_alignment_for_equal_lengths(wt_cds: str, var_cds: str) -> bool:
    """
    Detect equal-length compensating-offset cases that are better explained as
    indels than as a long series of substitutions.
    """
    wt_codons = _split_codons(wt_cds)
    var_codons = _split_codons(var_cds)
    if len(wt_codons) != len(var_codons) or not wt_codons:
        return False

    mismatch_positions = [idx for idx, (wc, vc) in enumerate(zip(wt_codons, var_codons)) if wc != vc]
    direct_mismatches = len(mismatch_positions)
    if direct_mismatches < 2:
        return False

    start = mismatch_positions[0]
    end = mismatch_positions[-1]
    mismatch_span = end - start + 1

    # Cheap check for a compact shifted block (for example, a single codon
    # insertion plus a compensating deletion) without paying for whole-CDS DP.
    if mismatch_span <= min(12, direct_mismatches + 4):
        wt_block = wt_codons[start : end + 1]
        var_block = var_codons[start : end + 1]
        max_shift = min(3, len(wt_block) - 1)
        for shift in range(1, max_shift + 1):
            if wt_block[shift:] == var_block[:-shift]:
                return True
            if wt_block[:-shift] == var_block[shift:]:
                return True

    if direct_mismatches < 6:
        return False

    # Most equal-length variants are simple substitutions. Only pay for the
    # codon-DP path when mismatches cluster in a way that suggests a shifted
    # block between a compensating insertion/deletion pair.
    if mismatch_span > direct_mismatches * 3:
        return False

    # Only align the mismatch region (with 2-codon padding) instead of the
    # full sequence — avoids O(n²) cost on 880-codon proteins.
    pad = 2
    block_start = max(0, start - pad)
    block_end = min(len(wt_codons), end + 1 + pad)

    # Hard cap: DP is only worthwhile for compact blocks. Larger spans are
    # virtually never a single insertion/deletion pair — bail out early.
    if block_end - block_start > 60:
        return False

    wt_block = wt_codons[block_start:block_end]
    var_block = var_codons[block_start:block_end]

    aligned_wt, aligned_var = _align_codons_global(wt_block, var_block)
    has_gap = any(a is None or b is None for a, b in zip(aligned_wt, aligned_var))
    if not has_gap:
        return False

    aligned_events = sum(1 for a, b in zip(aligned_wt, aligned_var) if a != b)
    # Compare against the number of mismatches in the block (not the whole CDS)
    block_mismatches = sum(1 for wc, vc in zip(wt_block, var_block) if wc != vc)
    return aligned_events <= block_mismatches


def _variant_cds_from_mapping(plasmid: str, mapping: WTMapping) -> str:
    """Extract CDS from a variant plasmid using the supplied mapping."""
    start = mapping.cds_start_0based
    end = mapping.cds_end_0based_excl
    n = len(plasmid)

    if start == end and len(mapping.wt_cds_dna) >= n:
        cds_dna = plasmid[start:] + plasmid[:start] if start != 0 else plasmid
    else:
        cds_dna = circular_slice(plasmid, start, end)

    if mapping.strand == "MINUS":
        cds_dna = reverse_complement_dna(cds_dna)

    return cds_dna


def _fast_anchor_remap(
    variant_plasmid: str,
    wt_mapping: WTMapping,
    *,
    anchor_len: int = 30,
    wt_plasmid: Optional[str] = None,
) -> Optional[WTMapping]:
    """Locate the CDS in a variant plasmid using backbone DNA anchors.

    In directed evolution the vector backbone (outside the CDS) is never
    mutated — only the CDS itself changes.  This function extracts a short
    DNA anchor from just upstream of the CDS start in the WT plasmid, finds
    that exact sequence in the variant plasmid, and derives the CDS
    coordinates from the anchor hit position.

    Falls back to ATG-scanning with N/C-terminal protein probes when no
    backbone anchor is available (e.g. when ``wt_plasmid`` is not provided
    or matches the CDS-only sequence stored in the DB).

    Returns a new WTMapping for the variant, or None if no anchor matches.
    """
    cds_len = len(wt_mapping.wt_cds_dna)
    if cds_len < 9:
        return None

    n = len(variant_plasmid)
    if n == 0:
        return None

    # ------------------------------------------------------------------
    # Strategy 1: Backbone DNA anchor (most reliable — works even with
    # 100% CDS mutation rate).
    # ------------------------------------------------------------------
    if wt_plasmid and len(wt_plasmid) > cds_len:
        wt_n = len(wt_plasmid)
        cds_start_wt = wt_mapping.cds_start_0based
        cds_end_wt = wt_mapping.cds_end_0based_excl

        # We need backbone DNA directly upstream of the CDS.
        # For PLUS strand: the anchor sits just before cds_start.
        # For MINUS strand: the anchor sits just after cds_end (on the
        #   plus strand), which is just before the CDS start in the RC.
        wt_doubled = wt_plasmid + wt_plasmid

        if wt_mapping.strand == "PLUS":
            # Upstream anchor: ends at cds_start
            anchor_end = cds_start_wt if cds_start_wt > 0 else wt_n
            anchor_start = anchor_end - anchor_len
            if anchor_start < 0:
                anchor_start += wt_n
                up_anchor = wt_doubled[anchor_start:anchor_start + anchor_len]
            else:
                up_anchor = wt_plasmid[anchor_start:anchor_end]

            # Downstream anchor: starts at cds_end
            dn_anchor_start = cds_end_wt
            dn_anchor = wt_doubled[dn_anchor_start:dn_anchor_start + anchor_len]

            # Search for both anchors in the variant plasmid
            var_doubled = variant_plasmid + variant_plasmid
            up_hit = var_doubled.find(up_anchor)
            dn_hit = var_doubled.find(dn_anchor)

            if up_hit >= 0 and up_hit < n:
                new_cds_start = (up_hit + anchor_len) % n
                if dn_hit >= 0 and dn_hit < 2 * n:
                    # Both anchors found — derive actual CDS length from
                    # the distance between them (handles indels correctly)
                    new_cds_end = dn_hit % n
                else:
                    # Only upstream anchor — assume WT CDS length
                    new_cds_end = (new_cds_start + cds_len) % n
                return WTMapping(
                    strand=wt_mapping.strand,
                    frame=wt_mapping.frame,
                    cds_start_0based=new_cds_start,
                    cds_end_0based_excl=new_cds_end,
                    wt_cds_dna=wt_mapping.wt_cds_dna,
                    wt_protein_aa=wt_mapping.wt_protein_aa,
                    match_identity_pct=wt_mapping.match_identity_pct,
                    alignment_score=wt_mapping.alignment_score,
                )

        elif wt_mapping.strand == "MINUS":
            # For MINUS strand, the CDS in the plus strand runs from
            # cds_start to cds_end (then we RC it).
            # Downstream anchor (after CDS end on plus strand):
            dn_anchor_start = cds_end_wt if cds_end_wt > 0 else 0
            dn_anchor = wt_doubled[dn_anchor_start:dn_anchor_start + anchor_len]
            # Upstream anchor (before CDS start on plus strand):
            up_anchor_end = cds_start_wt if cds_start_wt > 0 else wt_n
            up_anchor_start = up_anchor_end - anchor_len
            if up_anchor_start < 0:
                up_anchor_start += wt_n
                up_anchor = wt_doubled[up_anchor_start:up_anchor_start + anchor_len]
            else:
                up_anchor = wt_plasmid[up_anchor_start:up_anchor_end]

            var_doubled = variant_plasmid + variant_plasmid
            dn_hit = var_doubled.find(dn_anchor)
            up_hit = var_doubled.find(up_anchor)

            if dn_hit >= 0 and dn_hit < n:
                new_cds_end = dn_hit % n
                if up_hit >= 0 and up_hit < 2 * n:
                    new_cds_start = (up_hit + anchor_len) % n
                else:
                    new_cds_start = (new_cds_end - cds_len) % n
                return WTMapping(
                    strand=wt_mapping.strand,
                    frame=wt_mapping.frame,
                    cds_start_0based=new_cds_start,
                    cds_end_0based_excl=new_cds_end,
                    wt_cds_dna=wt_mapping.wt_cds_dna,
                    wt_protein_aa=wt_mapping.wt_protein_aa,
                    match_identity_pct=wt_mapping.match_identity_pct,
                    alignment_score=wt_mapping.alignment_score,
                )

    # ------------------------------------------------------------------
    # Strategy 2: ATG-scan with N/C-terminal protein probes (fallback
    # when no backbone anchor is available).
    # ------------------------------------------------------------------
    wt_prot = wt_mapping.wt_protein_aa
    n_probe = min(20, len(wt_prot))
    if n_probe < 3:
        return None
    min_match_frac = 0.70
    min_matches = int(n_probe * min_match_frac)

    doubled = variant_plasmid + variant_plasmid

    strands_to_try = []
    if wt_mapping.strand == "PLUS":
        strands_to_try.append(("PLUS", doubled))
    elif wt_mapping.strand == "MINUS":
        rc_doubled = reverse_complement_dna(doubled)
        strands_to_try.append(("MINUS", rc_doubled))
    else:
        strands_to_try.append(("PLUS", doubled))
        rc_doubled = reverse_complement_dna(doubled)
        strands_to_try.append(("MINUS", rc_doubled))

    best_hit: Optional[WTMapping] = None
    best_matches = min_matches - 1

    for strand_label, seq in strands_to_try:
        search_start = 0
        while True:
            atg_pos = seq.find("ATG", search_start)
            if atg_pos < 0 or atg_pos >= n:
                break
            search_start = atg_pos + 1

            candidate_end = atg_pos + cds_len
            if candidate_end > len(seq):
                continue
            candidate_cds = seq[atg_pos:candidate_end]
            if len(candidate_cds) != cds_len:
                continue

            probe_dna = candidate_cds[:n_probe * 3]
            try:
                probe_aa = "".join(
                    _translate_codon_cached(probe_dna[k:k + 3])
                    for k in range(0, len(probe_dna), 3)
                )
            except Exception:
                continue

            if not probe_aa or probe_aa[0] != "M":
                continue

            matches = sum(
                1 for j in range(n_probe) if probe_aa[j] == wt_prot[j]
            )
            if matches <= best_matches:
                continue

            c_probe_dna = candidate_cds[-n_probe * 3:]
            try:
                c_probe_aa = "".join(
                    _translate_codon_cached(c_probe_dna[k:k + 3])
                    for k in range(0, len(c_probe_dna), 3)
                )
                c_matches = sum(
                    1 for j in range(n_probe)
                    if c_probe_aa[j] == wt_prot[-(n_probe - j)]
                )
                if c_matches < min_matches:
                    continue
            except Exception:
                continue

            if strand_label == "PLUS":
                cds_start = atg_pos % n
            else:
                plus_pos_of_last_base = (2 * n - 1 - (atg_pos + cds_len - 1))
                cds_start = plus_pos_of_last_base % n

            cds_end = (cds_start + cds_len) % n

            best_matches = matches
            best_hit = WTMapping(
                strand=wt_mapping.strand,
                frame=wt_mapping.frame,
                cds_start_0based=cds_start,
                cds_end_0based_excl=cds_end,
                wt_cds_dna=wt_mapping.wt_cds_dna,
                wt_protein_aa=wt_mapping.wt_protein_aa,
                match_identity_pct=wt_mapping.match_identity_pct,
                alignment_score=wt_mapping.alignment_score,
            )

            if matches == n_probe:
                return best_hit

    return best_hit


def _translate_variant_cds(
    cds_dna: str, wt_protein_aa: str,
) -> Tuple[Optional[str], Optional[str], QCFlags]:
    """Translate extracted CDS once and return output protein, full protein, and QC.

    Translates with ``to_stop=False`` so a single translation provides both
    the stop-policy–compliant output protein *and* a full stop-free protein
    for alignment-based coordinate validation (remap detection).

    Returns:
        (output_protein, full_protein_no_stops, qc_flags)
    """
    has_frameshift = (len(cds_dna) % 3 != 0)
    has_ambig = contains_ambiguous_bases(cds_dna)

    protein: Optional[str] = None
    full_protein_no_stops: Optional[str] = None
    prem_stop = False
    notes: Optional[str] = None

    if cds_dna:
        try:
            # Single translation — derive everything from the full protein.
            full_translation = translate_dna(
                cds_dna,
                table=settings.GENETIC_CODE_TABLE,
                to_stop=False,
            )
            full_protein_no_stops = full_translation.replace("*", "")

            if "*" in full_translation:
                prem_stop = True
                if settings.STOP_POLICY == "truncate":
                    protein = full_translation.split("*")[0]
                    notes = "Protein truncated due to in-frame stop codon."
                else:
                    protein = full_translation
                    notes = "Stop codon(s) present in translated protein."
            else:
                protein = full_translation

        except Exception as e:
            protein = None
            full_protein_no_stops = None
            notes = f"Translation failed: {type(e).__name__}: {e}"

    qc = QCFlags(
        has_ambiguous_bases=has_ambig,
        has_frameshift=has_frameshift,
        has_premature_stop=prem_stop,
        notes=notes,
    )
    return protein, full_protein_no_stops, qc


def _quick_protein_match(
    protein_aa: str,
    wt_protein_aa: str,
    *,
    window: int = 20,
    min_identity: float = 0.80,
    max_length_ratio: float = 0.10,
) -> bool:
    """Fast O(1) pre-screen: CDS coordinates valid if length + terminal residues match.

    For directed-evolution variants the protein differs from WT by a handful of
    point mutations. If the N-terminal and C-terminal residues match the WT
    with ≥80 % identity and the overall length is within 10 %, the CDS
    coordinates are almost certainly correct. This avoids the expensive O(n²)
    BLOSUM62 local alignment that ``_needs_variant_remap`` would otherwise run
    for every single variant.
    """
    prot_len = len(protein_aa)
    wt_len = len(wt_protein_aa)

    # Length within tolerance?
    if abs(prot_len - wt_len) > max(10, int(wt_len * max_length_ratio)):
        return False

    # N-terminal identity
    n = min(window, prot_len, wt_len)
    n_matches = sum(1 for i in range(n) if protein_aa[i] == wt_protein_aa[i])
    if n_matches / max(1, n) < min_identity:
        return False

    # C-terminal identity
    c = min(window, prot_len, wt_len)
    c_matches = sum(1 for i in range(1, c + 1) if protein_aa[-i] == wt_protein_aa[-i])
    if c_matches / max(1, c) < min_identity:
        return False

    return True


def _needs_variant_remap(protein_aa: Optional[str], wt_protein_aa: str) -> bool:
    """
    Detects when fixed-coordinate extraction likely captured the wrong CDS window.

    Uses a fast O(1) terminal-residue pre-screen first.  Only falls through to
    the expensive BLOSUM62 local alignment when the pre-screen is inconclusive
    (short protein, length mismatch, or terminal mutations).
    """
    if not protein_aa:
        return True

    wt_len = max(1, len(wt_protein_aa))
    prot_len = len(protein_aa)

    # A tiny translated fragment is almost always the result of slicing the
    # wrong CDS window and hitting an early stop codon immediately.
    if prot_len < max(30, wt_len // 4):
        return True

    # Fast path — skip the expensive alignment for typical directed-evolution
    # variants whose terminals and length closely match WT.
    if _quick_protein_match(protein_aa, wt_protein_aa):
        return False

    # Medium path — simple position-by-position identity for same/similar
    # length proteins catches cases where terminal mutations trip up the
    # quick match but the CDS window is clearly correct.
    if abs(prot_len - wt_len) <= max(5, int(wt_len * 0.02)):
        overlap = min(prot_len, wt_len)
        matches = sum(1 for i in range(overlap)
                      if protein_aa[i] == wt_protein_aa[i])
        if matches / max(1, overlap) >= 0.50:
            return False

    # Slow path — only reached for atypical variants (large indels,
    # significant length changes, or terminal mutations).
    aln = _LOCAL_ALIGNER.align(protein_aa, wt_protein_aa)[0]
    if aln.aligned[0].size == 0 or aln.aligned[1].size == 0:
        return True

    aligned_wt = sum(
        int(t1) - int(t0)
        for t0, t1 in aln.aligned[1]
    )
    wt_coverage = aligned_wt / wt_len

    if prot_len < max(60, int(0.75 * wt_len)) and wt_coverage < 0.50:
        return True

    q0 = int(aln.aligned[0][0][0])
    t0 = int(aln.aligned[1][0][0])

    return abs(q0 - t0) > 5


# ============================================================================
# Main Sequence Processing Functions
# ============================================================================

def map_wt_gene_in_plasmid(wt_protein_aa: str, wt_plasmid_dna: str) -> WTMapping:
    """
    Locates the wild-type CDS within a circular plasmid using 6-frame
    protein alignment. See the project MkDocs (Visualisations > Step 1)
    for the full algorithm walkthrough and diagrams.

    Args:
        wt_protein_aa: Reference protein sequence (amino acids).
        wt_plasmid_dna: Circular plasmid DNA sequence.

    Returns:
        WTMapping: Best mapping with strand, frame, coordinates, sequences,
                   identity percentage, and alignment score.

    Raises:
        ValueError: If plasmid or protein is empty.
        RuntimeError: If no valid mapping found above identity threshold.
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

            aln = aligner.align(translated, wt_protein)[0]
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
        wt_plasmid: Optional[str] = None,
) -> VariantSeqResult:
    """
    Extracts, translates, and QC-checks the variant CDS using WT mapping
    coordinates. See the project MkDocs (Visualisations > Steps 2-3) for
    details.

    Args:
        variant_plasmid_dna: Variant plasmid DNA sequence.
        wt_mapping: Wild-type mapping with coordinates and orientation.
        fallback_search: If True, preserves a QC note when de novo remapping
                        is attempted but cannot recover a plausible CDS.
        wt_plasmid: Full WT plasmid DNA (enables backbone-anchor remap).

    Returns:
        VariantSeqResult: Extracted CDS, translated protein, and QC flags.
    """
    plasmid = normalise_dna(variant_plasmid_dna)
    active_mapping = wt_mapping
    cds_dna = _variant_cds_from_mapping(plasmid, active_mapping)
    protein, full_prot, qc = _translate_variant_cds(cds_dna, active_mapping.wt_protein_aa)

    # Fast pre-screen: if the quick match passes, coordinates are fine.
    prot_for_check = full_prot or protein
    if prot_for_check and _quick_protein_match(prot_for_check, active_mapping.wt_protein_aa):
        remap_needed = False
    else:
        # Before running the expensive BLOSUM62 remap check, try the fast
        # anchor-based remap.  This handles the common case where the variant
        # plasmid is a rotational offset of the WT plasmid.
        anchor_mapping = _fast_anchor_remap(plasmid, wt_mapping, wt_plasmid=wt_plasmid)
        if anchor_mapping is not None:
            active_mapping = anchor_mapping
            cds_dna = _variant_cds_from_mapping(plasmid, active_mapping)
            protein, full_prot, qc = _translate_variant_cds(cds_dna, active_mapping.wt_protein_aa)
            note = "Variant remapped via backbone anchor (rotational offset)."
            qc = QCFlags(
                has_ambiguous_bases=qc.has_ambiguous_bases,
                has_frameshift=qc.has_frameshift,
                has_premature_stop=qc.has_premature_stop,
                notes=(f"{note} {qc.notes}" if qc.notes else note),
            )
            remap_needed = False
        else:
            # Anchor remap failed — fall through to the expensive check.
            remap_needed = _needs_variant_remap(
                prot_for_check, active_mapping.wt_protein_aa,
            )

    # Only attempt de novo remap when the caller explicitly enables fallback search.
    if remap_needed and not fallback_search:
        note = "CDS coordinate drift suspected; de novo remap disabled (fallback_search=False)."
        qc = QCFlags(
            has_ambiguous_bases=qc.has_ambiguous_bases,
            has_frameshift=qc.has_frameshift,
            has_premature_stop=qc.has_premature_stop,
            notes=(f"{qc.notes} {note}" if qc.notes else note),
        )
        return VariantSeqResult(
            cds_start_0based=None,
            cds_end_0based_excl=None,
            strand=None,
            frame=None,
            cds_dna=None,
            protein_aa=None,
            qc=qc,
        )

    if remap_needed and fallback_search:
        try:
            # Anchor remap already failed in the pre-screen above, so go
            # directly to the expensive full 6-frame protein alignment.
            active_mapping = map_wt_gene_in_plasmid(active_mapping.wt_protein_aa, plasmid)
            cds_dna = active_mapping.wt_cds_dna
            protein, _, qc = _translate_variant_cds(cds_dna, active_mapping.wt_protein_aa)
            note = "Variant remapped de novo due to CDS coordinate drift."
            qc = QCFlags(
                has_ambiguous_bases=qc.has_ambiguous_bases,
                has_frameshift=qc.has_frameshift,
                has_premature_stop=qc.has_premature_stop,
                notes=(f"{note} {qc.notes}" if qc.notes else note),
            )
        except Exception as e:
            note = f"Variant remap failed: {type(e).__name__}: {e}"
            qc = QCFlags(
                has_ambiguous_bases=qc.has_ambiguous_bases,
                has_frameshift=qc.has_frameshift,
                has_premature_stop=qc.has_premature_stop,
                notes=(f"{qc.notes} {note}" if qc.notes else note),
            )
            # The fixed-coordinate slice is known bad at this point.
            # Return a QC-only failure so downstream mutation counting is skipped.
            return VariantSeqResult(
                cds_start_0based=None,
                cds_end_0based_excl=None,
                strand=None,
                frame=None,
                cds_dna=None,
                protein_aa=None,
                qc=qc,
            )

    return VariantSeqResult(
        cds_start_0based=active_mapping.cds_start_0based,
        cds_end_0based_excl=active_mapping.cds_end_0based_excl,
        strand=active_mapping.strand,
        frame=active_mapping.frame,
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
    Detect mutations in indel / offset cases using codon-aware global alignment.

    Despite the historical function name, this path now aligns codons directly
    so every codon-level event remains countable, including synonymous codon
    substitutions near insertions/deletions.

    Args:
        wt_cds_dna: Wild-type CDS DNA sequence.
        var_cds_dna: Variant CDS DNA sequence.

    Returns:
        Tuple of (List[MutationRecord], MutationCounts).
    """
    wt_cds = normalise_dna(wt_cds_dna)
    var_cds = normalise_dna(var_cds_dna)

    wt_codons = _split_codons(wt_cds)
    var_codons = _split_codons(var_cds)
    if not wt_codons and not var_codons:
        return ([], MutationCounts(synonymous=0, nonsynonymous=0, total=0))

    # ------------------------------------------------------------------
    # Prefix/suffix trimming: only align the mismatch block.
    # In directed evolution the vast majority of codons are identical;
    # trimming reduces the DP matrix from ~880×880 to ~30×30 or smaller.
    # ------------------------------------------------------------------
    prefix_len = 0
    min_len = min(len(wt_codons), len(var_codons))
    while prefix_len < min_len and wt_codons[prefix_len] == var_codons[prefix_len]:
        prefix_len += 1

    suffix_len = 0
    while (
        suffix_len < (min_len - prefix_len)
        and wt_codons[-(suffix_len + 1)] == var_codons[-(suffix_len + 1)]
    ):
        suffix_len += 1

    wt_end = len(wt_codons) - suffix_len
    var_end = len(var_codons) - suffix_len
    wt_block = wt_codons[prefix_len:wt_end]
    var_block = var_codons[prefix_len:var_end]

    if wt_block or var_block:
        # Cap the block size to avoid O(n²) blowup on pathological cases
        max_block = 60
        if len(wt_block) > max_block or len(var_block) > max_block:
            wt_block_aln, var_block_aln = _align_codons_global(wt_block, var_block)
        else:
            wt_block_aln, var_block_aln = _align_codons_global(wt_block, var_block)
        # Reconstruct full alignment: prefix (identity) + aligned block + suffix (identity)
        wt_aln: List[Optional[str]] = list(wt_codons[:prefix_len]) + wt_block_aln + list(wt_codons[wt_end:])
        var_aln: List[Optional[str]] = list(var_codons[:prefix_len]) + var_block_aln + list(var_codons[var_end:])
    else:
        # All codons match (lengths differ only by trailing codons handled above)
        wt_aln = list(wt_codons)
        var_aln = list(var_codons)

    muts: List[MutationRecord] = []
    syn = 0
    nonsyn = 0
    total = 0

    wt_pos = 0  # 1-based codon position in WT
    var_pos = 0  # 1-based codon position in variant

    for wt_codon, var_codon in zip(wt_aln, var_aln):
        if wt_codon is not None:
            wt_pos += 1
        if var_codon is not None:
            var_pos += 1

        if wt_codon is None and var_codon is not None:
            var_aa = (
                _translate_codon_cached(var_codon)
                if all(b in {"A", "T", "C", "G"} for b in var_codon)
                else None
            )
            total += 1
            nonsyn += 1
            muts.append(
                MutationRecord(
                    mutation_type="INSERTION",
                    codon_index_1based=var_pos,
                    aa_position_1based=var_pos,
                    wt_codon=None,
                    var_codon=var_codon,
                    wt_aa=None,
                    var_aa=var_aa,
                    notes="In-frame codon insertion (codon alignment).",
                )
            )
            continue

        if wt_codon is not None and var_codon is None:
            wt_aa = (
                _translate_codon_cached(wt_codon)
                if all(b in {"A", "T", "C", "G"} for b in wt_codon)
                else None
            )
            total += 1
            nonsyn += 1
            muts.append(
                MutationRecord(
                    mutation_type="DELETION",
                    codon_index_1based=wt_pos,
                    aa_position_1based=wt_pos,
                    wt_codon=wt_codon,
                    var_codon=None,
                    wt_aa=wt_aa,
                    var_aa=None,
                    notes="In-frame codon deletion (codon alignment).",
                )
            )
            continue

        # For aligned residues, compare codons first, not just amino acids.
        # This preserves synonymous codon substitutions in indel/offset cases.
        if wt_codon == var_codon:
            continue

        total += 1

        if any(b not in {"A", "T", "C", "G"} for b in (wt_codon or "") + (var_codon or "")):
            muts.append(
                MutationRecord(
                    mutation_type="AMBIGUOUS",
                    codon_index_1based=wt_pos,
                    aa_position_1based=wt_pos,
                    wt_codon=wt_codon,
                    var_codon=var_codon,
                    wt_aa=None,
                    var_aa=None,
                    notes="Ambiguous base(s) in codon-alignment mismatch.",
                )
            )
            continue

        wt_aa = _translate_codon_cached(wt_codon)
        var_aa = _translate_codon_cached(var_codon)

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
                codon_index_1based=wt_pos,
                aa_position_1based=wt_pos,
                wt_codon=wt_codon,
                var_codon=var_codon,
                wt_aa=wt_aa,
                var_aa=var_aa,
                notes=None,
            )
        )

    return muts, MutationCounts(synonymous=syn, nonsynonymous=nonsyn, total=total)

    
def call_mutations_against_wt(
        wt_cds_dna: str,
        var_cds_dna: str,
) -> Tuple[List[MutationRecord], MutationCounts]:
    """
    Main mutation calling entry point — selects codon-by-codon or protein
    alignment strategy automatically. See the project MkDocs
    (Visualisations > Step 4) for the strategy diagram.

    Args:
        wt_cds_dna: Wild-type CDS DNA sequence.
        var_cds_dna: Variant CDS DNA sequence.

    Returns:
        Tuple of (List[MutationRecord], MutationCounts).
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

    # Equal-length CDS can still hide a compensating internal indel. Use the
    # same codon-aware alignment logic to decide whether the sequence is better
    # explained as insertion/deletion events than as a long substitution chain.
    if _prefer_codon_alignment_for_equal_lengths(wt, var):
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

        wt_aa = _translate_codon_cached(wt_codon)
        var_aa = _translate_codon_cached(var_codon)

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
