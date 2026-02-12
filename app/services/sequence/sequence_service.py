from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Optional

from Bio.Align import PairwiseAligner
from Bio.Align import substitution_matrices

from app.config import settings
from .seq_utils import (
    normalise_dna,
    reverse_complement,
    circular_slice,
    contains_ambiguous_bases,
    translate_dna,
)

@dataclass(frozen=True)
class WTMapping:
    strand: str # "PLUS" or "MINUS"
    frame: int # 0|1|2
    cds_start_0based: int
    cds_end_0based_excl: int
    wt_cds_dna: str
    wt_protein_aa: str
    match_identity_pct: float
    alignment_score: float

@dataclass(frozen=True)
class QCFlags:
    has_ambiguous_bases: bool
    has_frameshift: bool
    has_premature_stop: bool
    notes: Optional[str] = None

@dataclass(frozen=True)
class VariantSeqResult:
    cds_start_0based: Optional[int]
    cds_end_0based_excl: Optional[int]
    strand: Optional[str]
    frame: Optional[int]
    cds_dna: Optional[str]
    protein_aa: Optional[str]
    qc: QCFlags

@dataclass(frozen=True)
class MutationRecord:
    mutation_type: str # "SYNONYMOUS", "MISSENSE", "NONSENSE", "FRAMESHIFT", "INSERTION", "DELETION", "AMBIGUOUS"
    codon_index_1based: Optional[int]
    aa_position_1based: Optional[int]
    wt_codon: Optional[str]
    var_codon: Optional[str]
    wt_aa: Optional[str]
    var_aa: Optional[str]
    notes: Optional[str] = None

@dataclass(frozen=True)
class MutationCounts:
    synonymous: int
    nonsynonymous: int
    total: int

# WT mapping

def map_wt_gene_in_plasmid(wt_protein_aa: str, wt_plasmid_dna: str) -> WTMapping:
    """
    Identify the WT CDS inside a circular plasmid using protein-guided 6-frame
    alignment
    """
    wt_protein_aa = wt_protein_aa.strip().upper()
    plasmid = normalise_dna(wt_plasmid_dna)

    if not plasmid:
        raise ValueError("WT plasmid sequence is empty.")
    
    n = len(plasmid)

    # Simulate circular plasmid 
    circular = plasmid + plasmid

    aligner = _make_protein_aligner()

    best_score = float("-inf")
    best_identity = 0.0
    best_alignment_score = 0.0
    best_mapping = None

    strands = {
        "PLUS": circular,
        "MINUS": reverse_complement(circular),
    }

    for strand_name, seq in strands.items():

        for frame in (0, 1, 2):

            translated = str(
                translate_dna(
                    seq[frame:],
                    table=settings.GENETIC_CODE_TABLE,
                    to_stop=False,
                )
            )

            if not translated:
                continue

            alignment = aligner.align(translated, wt_protein_aa)[0]

            aligned_query, aligned_target = alignment.format().split("\n")[0], alignment.format().split("\n")[2]

            matches = sum(
                1 for a, b in zip(aligned_query, aligned_target) if a == b and a != "-")
            
            aligned_len = sum(
                1 for a, b in zip (aligned_query, aligned_target) if a != "-" and b != "-")
            
            if aligned_len == 0:
                continue

            identity_pct = (matches / aligned_len) * 100.0

            if identity_pct < settings.WT_MIN_IDENTITY_PCT:
                continue

            if alignment.score > best_score:
                best_score = alignment.score
                best_identity = identity_pct
                best_alignment_score = float(alignment.score)

                # Determine protein start index in translated sequence
                prot_start = alignment.aligned[0][0][0]

                nt_start = frame + (prot_start * 3)
                nt_end = nt_start + (len(wt_protein_aa) * 3)

                # Map back to original plasmid coordinates 
                nt_start_mod = nt_start % n
                nt_end_mod = nt_end % n

                wt_cds = circular_slice(
                    plasmid,
                    nt_start_mod,
                    nt_end_mod,
                )

                if strand_name == "MINUS":
                    wt_cds = reverse_complement(wt_cds)

                best_mapping = WTMapping(
                    strand=strand_name,
                    frame=frame,
                    cds_start_0based=nt_start_mod,
                    cds_end_0based_excl=nt_end_mod,
                    wt_cds_dna=wt_cds,
                    wt_protein_aa=wt_protein_aa,
                    match_identity_pct=identity_pct,
                    alignment_score=best_alignment_score,
                )
        if best_mapping is None:
            raise RuntimeError(
                "Unable to locate WT CDS in plasmid above identity threshold."
            )
        
        return best_mapping


# Variant processing

def process_variant_plasmid(
        variant_plasmid_dna: str,
        wt_mapping: WTMapping,
        *,
        fallback_search: bool,
) -> VariantSeqResult:
    """
    Extracts variant CDS using WT mapping coordinates, translate, then QC.
    """
    variant_plasmid_dna = normalise_dna(variant_plasmid_dna)

    # 1) Slice using WT coordinates (supports circular plasmids)
    cds_dna = circular_slice(
        variant_plasmid_dna,
        wt_mapping.cds_start_0based,
        wt_mapping.cds_end_0based_excl,
    )
    
    # 2) Apply strand
    if wt_mapping.strand == "MINUS":
        cds_dna = reverse_complement(cds_dna)

    # 3) Apply frame by trimming leading bases
    if wt_mapping.frame in (0,1,2):
        cds_dna = cds_dna[wt_mapping.frame:]
    has_frameshift = (len(cds_dna) % 3 != 0)
    has_ambig = contains_ambiguous_bases(cds_dna)


    # Translation policy
    to_stop = (settings.STOP_POLICY == "truncate")
    protein: Optional[str] = None
    prem_stop = False
    notes: Optional[str] = None

    if cds_dna:
        try:
            protein = translate_dna(cds_dna, table=settings.GENETIC_CODE_TABLE, to_stop=to_stop,)

            if settings.STOP_POLICY != "truncate" and protein and "*" in protein:
                prem_stop = True
                notes = "Stop codon(s) present in translated protein."

            if settings.STOP_POLICY == "truncate" and protein:
                # if protein length is shorter than WT, then treat as premature stop
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
        # Future extension : re-map CDS via protein alignment search
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

# Indel alignment helpers

def _make_protein_aligner() -> PairwiseAligner:
    aligner = PairwiseAligner()
    aligner.mode = "global"
    aligner.substitution_matrix = substitution_matrices.load("BLOSUM62")
    aligner.open_gap_score = -10.0
    aligner.extend_gap_score = -0.5
    return aligner

def _safe_codon(dna: str, codon_index_1based: Optional[int]) -> Optional[str]:
    if codon_index_1based is None:
        return None
    i0 = (codon_index_1based -1) * 3
    i1 = i0 + 3
    if i1 > len(dna):
        return None
    return dna[i0:i1]

# Mutation calling

def call_mutation_via_protein_alignment(
        wt_cds_dna: str,
        var_cds_dna: str, 
) -> Tuple[List[MutationRecord], MutationCounts]:
    
    wt_prot = translate_dna(
        wt_cds_dna,
        table=settings.GENETIC_CODE_TABLE,
        to_stop=False,
    )

    var_prot = translate_dna(
        var_cds_dna,
        table=settings.GENETIC_CODE_TABLE,
        to_stop=False,
    )

    aligner = _make_protein_aligner()
    alignment = aligner.align(wt_prot, var_prot)[0]

    # Extract gapped strings from alignment
    lines = alignment.format().split("\n")
    wt_aln = lines[0]
    var_aln = lines[2]

    muts: List[MutationRecord] = []
    syn = 0
    nonsyn = 0
    total = 0

    wt_aa_pos = 0
    var_aa_pos = 0

    for wa, va in zip(wt_aln, var_aln):

        if wa != "-":
            wt_aa_pos += 1
        if va != "-":
            var_aa_pos += 1

        # Insertion
        if wa == "-" and va != "-":
            total += 1
            muts.append(
                MutationRecord(
                    mutation_type="INSERTION",
                    codon_index_1based=var_aa_pos,
                    aa_position_1based=var_aa_pos,
                    wt_codon=None,
                    var_codon=_safe_codon(var_cds_dna, var_aa_pos),
                    wt_aa=None,
                    var_aa=va,
                    notes="In-frame insertion (protein alignment)."
                )
            )
            continue

        # Deletion
        if wa != "-" and va == "-":
            total += 1
            muts.append(
                MutationRecord(
                    mutation_type="DELETION",
                    codon_index_1based=wt_aa_pos,
                    aa_position_1based=wt_aa_pos,
                    wt_codon=_safe_codon(wt_cds_dna, wt_aa_pos), 
                    var_codon=None,
                    wt_aa=wa,
                    var_aa=None,
                    notes="In-frame deletion (protein alignment)."
                )
            )
            continue

        if wa == va:
            continue

        total += 1

        wt_codon = _safe_codon(wt_cds_dna, wt_aa_pos)
        var_codon = _safe_codon(var_cds_dna, var_aa_pos)

        if wt_codon and var_codon:
            wt_aa = translate_dna(
                wt_codon,
                table=settings.GENETIC_CODE_TABLE,
                to_stop=False,
            )

            var_aa = translate_dna(
                var_codon,
                table=settings.GENETIC_CODE_TABLE,
                to_stop=False,
            )

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
            mtype = "NONSYNONYMOUS"
            nonsyn += 1

        muts.append(
            MutationRecord(
                mutation_type=mtype,
                codon_index_1based=wt_aa_pos,
                aa_position_1based=wt_aa_pos,
                wt_codon=wt_codon,
                var_codon=var_codon,
                wt_aa=wa,
                var_aa=va,
                notes=None
            )
        )

    return muts, MutationCounts(syn, nonsyn, total)


def call_mutations_against_wt(
        wt_cds_dna: str,
        var_cds_dna: str,
) -> Tuple[List[MutationRecord], MutationCounts]:

    wt = normalise_dna(wt_cds_dna)
    var = normalise_dna(var_cds_dna)

    # Frameshift
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
        
    # In-frame indels
    if len(wt) != len(var):
        return call_mutation_via_protein_alignment(wt_cds_dna, var_cds_dna)

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

        wt_aa = translate_dna(
            wt_codon,
            table=settings.GENETIC_CODE_TABLE,
            to_stop=False,
        )
        var_aa = translate_dna(
            var_codon, 
            table=settings.GENETIC_CODE_TABLE,
            to_stop=False,
        )

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

    return muts, MutationCounts(syn, nonsyn, total)