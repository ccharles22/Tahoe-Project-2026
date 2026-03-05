"""Plasmid-vs-WT validation using translated-frame local alignment.

Validates that a circular plasmid DNA sequence encodes a given wild-type
protein.  First attempts an exact substring match across all six reading
frames; if none is found, performs local alignment and evaluates identity
and coverage thresholds.
"""

from __future__ import annotations

from dataclasses import dataclass

from Bio.Align import PairwiseAligner
from Bio.Seq import Seq
from app.services.sequence.seq_utils import DEFAULT_GENETIC_CODE_TABLE


@dataclass
class ValidationResult:
    """Structured validation outcome returned to staging routes."""

    is_valid: bool
    identity: float
    coverage: float
    strand: str
    start_nt: int
    end_nt: int
    wraps: bool
    message: str
    genetic_code_used: int = DEFAULT_GENETIC_CODE_TABLE


def reverse_complement(dna: str) -> str:
    """Return reverse complement of a DNA sequence."""
    return str(Seq(dna).reverse_complement())


def translate_frame(
    dna: str,
    frame: int = 0,
    genetic_code_table: int = DEFAULT_GENETIC_CODE_TABLE,
    cds: bool = False,
) -> str:
    """Translate DNA from a reading frame index (0, 1, or 2).

    Trims trailing bases that do not form a complete codon before
    translation.

    Args:
        dna: DNA sequence string.
        frame: Reading-frame offset (0, 1, or 2).
        genetic_code_table: NCBI genetic-code table number.
        cds: If True, use Biopython's CDS translation mode.

    Returns:
        Translated protein string, or empty string if the frame is too short.
    """
    frame_seq = dna[frame:]
    trimmed_len = len(frame_seq) - (len(frame_seq) % 3)
    if trimmed_len <= 0:
        return ''
    return str(
        Seq(frame_seq[:trimmed_len]).translate(
            table=genetic_code_table,
            to_stop=False,
            cds=cds,
        )
    )


def _make_local_aligner() -> PairwiseAligner:
    """Build a local aligner tuned for approximate protein-in-plasmid matching."""
    aligner = PairwiseAligner()
    aligner.mode = 'local'
    aligner.match_score = 2.0
    aligner.mismatch_score = -1.0
    aligner.open_gap_score = -5.0
    aligner.extend_gap_score = -1.0
    return aligner


def _best_local_alignment(
    query: str,
    target: str,
    aligner: PairwiseAligner,
) -> tuple[float, float, int, int]:
    """Find the top-scoring local alignment and compute identity/coverage.

    Args:
        query: Query protein sequence (WT).
        target: Target protein sequence (translated frame).
        aligner: Pre-configured ``PairwiseAligner``.

    Returns:
        Tuple of (identity_pct, coverage_pct, target_start_aa, target_end_aa).
    """
    alignments = aligner.align(target, query)
    if len(alignments) == 0:
        return 0.0, 0.0, 0, 0
    best = alignments[0]

    t_segs, q_segs = best.aligned
    if len(t_segs) == 0 or len(q_segs) == 0:
        return 0.0, 0.0, 0, 0

    matches = 0
    aligned_len = 0
    query_covered = 0

    for (t0, t1), (q0, q1) in zip(t_segs, q_segs):
        seg_len = min(t1 - t0, q1 - q0)
        t_chunk = target[t0 : t0 + seg_len]
        q_chunk = query[q0 : q0 + seg_len]
        for a, b in zip(t_chunk, q_chunk):
            if a == b:
                matches += 1
        aligned_len += seg_len
        query_covered += seg_len

    if aligned_len == 0:
        return 0.0, 0.0, 0, 0

    identity_pct = (matches / aligned_len) * 100.0
    coverage_pct = (query_covered / len(query)) * 100.0
    target_start = min(t0 for (t0, _) in t_segs)
    target_end = max(t1 for (_, t1) in t_segs)
    return identity_pct, coverage_pct, target_start, target_end


def _map_hit_to_plasmid_coords(
    dna_length: int,
    source: str,
    frame: int,
    start_aa: int,
    end_aa: int,
) -> tuple[int, int, bool]:
    """Convert frame-space AA coordinates back to 0-based circular plasmid nt coords.

    Maps alignment coordinates (which refer to positions in a doubled,
    frame-shifted translation) back to original single-copy plasmid
    nucleotide positions.

    Args:
        dna_length: Length of the original (single-copy) plasmid.
        source: ``'fwd'`` or ``'rev'`` indicating strand used.
        frame: Reading-frame offset (0, 1, or 2).
        start_aa: Start amino-acid position in the translated frame.
        end_aa: End amino-acid position (exclusive).

    Returns:
        Tuple of (start_nt, end_nt, wraps) where *wraps* is True if the
        region spans the plasmid origin.
    """
    start_nt_s2 = frame + start_aa * 3
    end_nt_s2_excl = frame + end_aa * 3
    len_s2 = dna_length * 2

    if source == 'rev':
        s2_start = len_s2 - end_nt_s2_excl
        s2_end_excl = len_s2 - start_nt_s2
    else:
        s2_start = start_nt_s2
        s2_end_excl = end_nt_s2_excl

    start_nt = s2_start % dna_length
    end_nt = (s2_end_excl - 1) % dna_length
    wraps = (s2_start < dna_length) and (s2_end_excl > dna_length)
    return start_nt, end_nt, wraps


def validate_plasmid(
    wt_protein: str,
    plasmid_dna: str,
    min_identity: float = 98.0,
    min_coverage: float = 98.0,
    require_exact: bool = True,
    genetic_code_table: int = DEFAULT_GENETIC_CODE_TABLE,
) -> ValidationResult:
    """Validate that circular plasmid DNA encodes WT protein in one of six frames.

    Strategy:
        1. Translate the doubled plasmid in all six frames.
        2. Attempt exact substring match of the WT protein in each frame.
        3. If no exact match, fall back to local alignment scoring.
        4. Report identity, coverage, strand, and coordinates.

    Args:
        wt_protein: Reference protein sequence.
        plasmid_dna: Circular plasmid DNA sequence.
        min_identity: Minimum percent identity for approximate pass.
        min_coverage: Minimum percent coverage for approximate pass.
        require_exact: If True, only exact matches produce a PASS result.
        genetic_code_table: NCBI genetic code table number.

    Returns:
        ValidationResult: Structured outcome with PASS/FAIL status,
            alignment statistics, and human-readable message.
    """
    protein = wt_protein.strip().upper()
    dna = plasmid_dna.strip().upper()

    if not protein:
        return ValidationResult(False, 0, 0, '+', 0, 0, False, 'WT protein sequence missing.')
    if not dna:
        return ValidationResult(False, 0, 0, '+', 0, 0, False, 'Plasmid DNA sequence missing.')

    length = len(dna)
    dna2 = dna + dna
    dna2_rc = reverse_complement(dna2)
    aligner = _make_local_aligner()

    best = {
        'identity': 0.0,
        'coverage': 0.0,
        'strand': '+',
        'frame': 0,
        'start_aa': 0,
        'end_aa': 0,
        'source': 'fwd',
    }

    translated_frames = []
    for source, strand, seq in (('fwd', '+', dna2), ('rev', '-', dna2_rc)):
        for frame in (0, 1, 2):
            translated = translate_frame(seq, frame, genetic_code_table=genetic_code_table)
            translated_frames.append((source, strand, frame, translated))
            exact_start = translated.find(protein)
            if exact_start >= 0:
                exact_end = exact_start + len(protein)
                start_nt, end_nt, wraps = _map_hit_to_plasmid_coords(
                    dna_length=length,
                    source=source,
                    frame=frame,
                    start_aa=exact_start,
                    end_aa=exact_end,
                )
                return ValidationResult(
                    is_valid=True,
                    identity=100.0,
                    coverage=100.0,
                    strand=strand,
                    start_nt=start_nt,
                    end_nt=end_nt,
                    wraps=wraps,
                    message='PASS: WT protein is exactly encoded in the uploaded plasmid.',
                    genetic_code_used=genetic_code_table,
                )

    for source, strand, frame, translated in translated_frames:
        identity, coverage, start_aa, end_aa = _best_local_alignment(
            protein,
            translated,
            aligner,
        )
        if (coverage, identity) > (best['coverage'], best['identity']):
            best.update(
                {
                    'identity': identity,
                    'coverage': coverage,
                    'strand': strand,
                    'frame': frame,
                    'start_aa': start_aa,
                    'end_aa': end_aa,
                    'source': source,
                }
            )

    start_nt, end_nt, wraps = _map_hit_to_plasmid_coords(
        dna_length=length,
        source=best['source'],
        frame=best['frame'],
        start_aa=best['start_aa'],
        end_aa=best['end_aa'],
    )
    approx_valid = (best['identity'] >= min_identity) and (best['coverage'] >= min_coverage)
    is_valid = approx_valid and not require_exact

    if is_valid:
        message = (
            f"PASS: Approximate match satisfies thresholds "
            f"({best['identity']:.1f}% identity, {best['coverage']:.1f}% coverage)."
        )
    else:
        exact_note = 'No exact WT protein encoding found across six translated frames. '
        message = (
            f"FAIL. {exact_note}Best hit: identity={best['identity']:.1f}%, coverage={best['coverage']:.1f}% "
            f"on strand {best['strand']} frame {best['frame']}."
        )

    return ValidationResult(
        is_valid=bool(is_valid),
        identity=float(best['identity']),
        coverage=float(best['coverage']),
        strand=str(best['strand']),
        start_nt=int(start_nt),
        end_nt=int(end_nt),
        wraps=bool(wraps),
        message=message,
        genetic_code_used=genetic_code_table,
    )
