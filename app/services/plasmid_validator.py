from dataclasses import dataclass
from typing import Optional, Dict, Any, Tuple
from Bio.Seq import Seq
from Bio.Align import PairwiseAligner


@dataclass
class ValidationResult:
    is_valid: bool
    identity: float
    coverage: float
    strand: str
    start_nt: int
    end_nt: int
    wraps: bool
    message: str

# Helper functions for DNA/protein processing and alignment
def reverse_complement(dna: str) -> str:
    return str(Seq(dna).reverse_complement())

def translate_frame(dna: str, frame: int = 0) -> str:
    # frame = 0,1,2
    return str(Seq(dna[frame:]).translate(to_stop=False))

def _best_local_alignment(query: str, target: str) -> Tuple[float, float, int, int]:
    """
    Local align query (WT protein) to target (translated frame).
    Returns:
      identity_pct, coverage_pct, target_start_aa, target_end_aa (end exclusive)
    """
    aligner = PairwiseAligner()
    aligner.mode = "local"
    aligner.match_score = 2.0 # reward for match 
    aligner.mismatch_score = -1.0 # penalty for mismatch
    aligner.open_gap_score = -5.0 # penalty for opening a gap
    aligner.extend_gap_score = -1.0 # penalty for extending a gap

    best = None
    best_score = float("-inf") 

    # PairwiseAligner returns Alignment objects; pick best by score
    for aln in aligner.align(target, query):  # note order: target vs query
        if aln.score > best_score:
            best_score = aln.score
            best = aln

    if best is None:
        return 0.0, 0.0, 0, 0 # no alignment found

    # Extract aligned slices from the alignment coordinate blocks
    # aligned segments are in best.aligned: (target_segments, query_segments)
    t_segs, q_segs = best.aligned
    if len(t_segs) == 0 or len(q_segs) == 0:
        return 0.0, 0.0, 0, 0

    # Build the aligned strings over segments to compute identity and coverage
    matches = 0
    aligned_len = 0
    query_covered = 0

    for (t0, t1), (q0, q1) in zip(t_segs, q_segs):
        # segment lengths should match
        seg_len = min(t1 - t0, q1 - q0) # safety check
        t_chunk = target[t0:t0 + seg_len] # target segment
        q_chunk = query[q0:q0 + seg_len] # query segment

        # count matches
        for a, b in zip(t_chunk, q_chunk):
            if a == b:
                matches += 1
        aligned_len += seg_len
        query_covered += seg_len

    # Avoid division by zero
    if aligned_len == 0:
        return 0.0, 0.0, 0, 0

    identity_pct = (matches / aligned_len) * 100.0 # identity percentage
    coverage_pct = (query_covered / len(query)) * 100.0 # coverage percentage

    # Determine target AA span from segments
    target_start = min(t0 for (t0, _) in t_segs)
    target_end = max(t1 for (_, t1) in t_segs)

    return identity_pct, coverage_pct, target_start, target_end # end exclusive

# Main validation function 
def validate_plasmid(
    wt_protein: str,
    plasmid_dna: str,
    min_identity: float = 98.0,
    min_coverage: float = 98.0
) -> ValidationResult:
    """
    Validates whether plasmid encodes WT protein somewhere on circular DNA.
    Uses S2=S+S and searches all 6 frames with local alignment.
    """

    P = wt_protein.strip().upper() # WT protein sequence
    S = plasmid_dna.strip().upper() # Plasmid DNA sequence

    if not P:
        return ValidationResult(False, 0, 0, "+", 0, 0, False, "WT protein sequence missing.")
    if not S:
        return ValidationResult(False, 0, 0, "+", 0, 0, False, "Plasmid DNA sequence missing.")

    L = len(S)
    S2 = S + S
    S2_rc = reverse_complement(S2)

    best: Dict[str, Any] = {
        "identity": 0.0, # best identity %
        "coverage": 0.0, # best coverage %
        "strand": "+", # best strand
        "frame": 0, # best frame
        "start_aa": 0, # best start AA index
        "end_aa": 0, # best end AA index
        "source": "fwd", # "fwd" or "rev" 
    }

    # Search forward frames
    for frame in (0, 1, 2):
        prot = translate_frame(S2, frame)
        identity, coverage, start_aa, end_aa = _best_local_alignment(P, prot)
        if (coverage, identity) > (best["coverage"], best["identity"]):
            best.update({
                "identity": identity,
                "coverage": coverage,
                "strand": "+",
                "frame": frame,
                "start_aa": start_aa,
                "end_aa": end_aa,
                "source": "fwd",
            })

    # Search reverse-complement frames
    for frame in (0, 1, 2):
        prot = translate_frame(S2_rc, frame)
        identity, coverage, start_aa, end_aa = _best_local_alignment(P, prot)
        if (coverage, identity) > (best["coverage"], best["identity"]):
            best.update({
                "identity": identity,
                "coverage": coverage,
                "strand": "-",
                "frame": frame,
                "start_aa": start_aa,
                "end_aa": end_aa,
                "source": "rev",
            })

    # Convert AA coords on S2 back to nt coords on original plasmid
    # AA index -> nt index on S2: nt = frame + aa*3
    start_nt_s2 = best["frame"] + best["start_aa"] * 3
    end_nt_s2_excl = best["frame"] + best["end_aa"] * 3  # end exclusive

    # Map to original plasmid coords [0, L)
    len_s2 = len(S2)  # = 2 * L

    # If the best hit came from reverse-complement translation, convert coords
    # from S2_rc space back into S2 space.
    if best["source"] == "rev":
        s2_start = len_s2 - end_nt_s2_excl
        s2_end_excl = len_s2 - start_nt_s2
    else:
        s2_start = start_nt_s2
        s2_end_excl = end_nt_s2_excl

    # Map to original plasmid coords [0, L)
    start_nt = s2_start % L
    end_nt = (s2_end_excl - 1) % L  # inclusive end for display

    # Wraps if alignment crosses the boundary between the first and second copy of S
    wraps = (s2_start < L) and (s2_end_excl > L)
    is_valid = (best["identity"] >= min_identity) and (best["coverage"] >= min_coverage)

    msg = (
        f"Best hit: identity={best['identity']:.1f}%, coverage={best['coverage']:.1f}% "
        f"on strand {best['strand']} frame {best['frame']}." 
    )
    if is_valid:
        msg = "PASS. " + msg # successful validation
    else:
        msg = "FAIL. " + msg # failed validation


    # Return structured result
    return ValidationResult(
        is_valid=is_valid,
        identity=best["identity"],
        coverage=best["coverage"],
        strand=best["strand"],
        start_nt=int(start_nt),
        end_nt=int(end_nt),
        wraps=wraps,
        message=msg
    )
