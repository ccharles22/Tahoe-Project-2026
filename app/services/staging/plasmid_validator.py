"""Plasmid-vs-WT validation using translated-frame local alignment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from Bio.Align import PairwiseAligner
from Bio.Seq import Seq


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


def reverse_complement(dna: str) -> str:
    """Return reverse complement of a DNA sequence."""
    return str(Seq(dna).reverse_complement())


def translate_frame(dna: str, frame: int = 0) -> str:
    """Translate DNA from a reading frame index (0, 1, or 2)."""
    return str(Seq(dna[frame:]).translate(to_stop=False))


def _best_local_alignment(query: str, target: str) -> tuple[float, float, int, int]:
    """Find best local alignment and return identity/coverage and target span."""
    aligner = PairwiseAligner()
    aligner.mode = 'local'
    aligner.match_score = 2.0
    aligner.mismatch_score = -1.0
    aligner.open_gap_score = -5.0
    aligner.extend_gap_score = -1.0

    best = None
    best_score = float('-inf')
    for aln in aligner.align(target, query):
        if aln.score > best_score:
            best_score = aln.score
            best = aln

    if best is None:
        return 0.0, 0.0, 0, 0

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


def validate_plasmid(
    wt_protein: str,
    plasmid_dna: str,
    min_identity: float = 98.0,
    min_coverage: float = 98.0,
) -> ValidationResult:
    """Validate that circular plasmid DNA encodes WT protein in one of six frames."""
    protein = wt_protein.strip().upper()
    dna = plasmid_dna.strip().upper()

    if not protein:
        return ValidationResult(False, 0, 0, '+', 0, 0, False, 'WT protein sequence missing.')
    if not dna:
        return ValidationResult(False, 0, 0, '+', 0, 0, False, 'Plasmid DNA sequence missing.')

    length = len(dna)
    dna2 = dna + dna
    dna2_rc = reverse_complement(dna2)

    best: dict[str, Any] = {
        'identity': 0.0,
        'coverage': 0.0,
        'strand': '+',
        'frame': 0,
        'start_aa': 0,
        'end_aa': 0,
        'source': 'fwd',
    }

    for frame in (0, 1, 2):
        translated = translate_frame(dna2, frame)
        identity, coverage, start_aa, end_aa = _best_local_alignment(protein, translated)
        if (coverage, identity) > (best['coverage'], best['identity']):
            best.update(
                {
                    'identity': identity,
                    'coverage': coverage,
                    'strand': '+',
                    'frame': frame,
                    'start_aa': start_aa,
                    'end_aa': end_aa,
                    'source': 'fwd',
                }
            )

    for frame in (0, 1, 2):
        translated = translate_frame(dna2_rc, frame)
        identity, coverage, start_aa, end_aa = _best_local_alignment(protein, translated)
        if (coverage, identity) > (best['coverage'], best['identity']):
            best.update(
                {
                    'identity': identity,
                    'coverage': coverage,
                    'strand': '-',
                    'frame': frame,
                    'start_aa': start_aa,
                    'end_aa': end_aa,
                    'source': 'rev',
                }
            )

    start_nt_s2 = best['frame'] + best['start_aa'] * 3
    end_nt_s2_excl = best['frame'] + best['end_aa'] * 3
    len_s2 = len(dna2)

    if best['source'] == 'rev':
        s2_start = len_s2 - end_nt_s2_excl
        s2_end_excl = len_s2 - start_nt_s2
    else:
        s2_start = start_nt_s2
        s2_end_excl = end_nt_s2_excl

    start_nt = s2_start % length
    end_nt = (s2_end_excl - 1) % length
    wraps = (s2_start < length) and (s2_end_excl > length)
    is_valid = (best['identity'] >= min_identity) and (best['coverage'] >= min_coverage)

    if is_valid:
        message = (
            f"PASS: Exact match to the expected WT CDS "
            f"({best['identity']:.1f}% identity, {best['coverage']:.1f}% coverage)."
        )
    else:
        message = (
            f"FAIL. Best hit: identity={best['identity']:.1f}%, coverage={best['coverage']:.1f}% "
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
    )
