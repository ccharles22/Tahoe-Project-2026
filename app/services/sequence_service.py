from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Optional

from app.config import settings
from app.utils.seq_utils import (
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
    The purpose of this function is implement protein guided gene identification via:
    - handling circular plasmid (e.g. plasmid+plasmid)
    - find 6 frames (3 forward and 3 reverse)
    - locally align translated segments to wt_protein_aa
    - choose best match above identity threshold 
    - convert to nucleotide coordinates and extract WT CDS DNA
    - translate CDS and compute identity.
    """
    raise NotImplementedError ("WT gene mapping not implemented yet.") # raise command used to force implementation before use

# Variant processing
def process_variant_plasmid(
        variant_plasmid_dna: str,
        wt_mapping: WTMapping,
        *,
        fallback_search: bool,
) -> VariantSeqResult:
    """
    extracts the variant CDS DNA and translates them to protein.
    Then Perform QC checks to find ambiguous bases, frameshifts and premature stops.

    If initial extraction fails QC and fallback_search is True, re-attempt gene finding
    with a slower but more sensitive method.
    """
    variant_plasmid_dna = normalise_dna(variant_plasmid_dna)

    # 1) Extract the variant CDS using the either the WT coordinates, strand or frame 
    cds_dna = circular_slice(
        variant_plasmid_dna,
        wt_mapping.cds_start_0based,
        wt_mapping.cds_end_0based_excl,
    )
    
    # 2) account for strand
    if wt_mapping.strand == "MINUS":
        cds_dna = reverse_complement(cds_dna)

    # 3) apply fram (0/1/2) by trimming prefix
    if wt_mapping.frame in (0,1,2):
        cds_dna = cds_dna[wt_mapping.frame:]
    else:
        # shouldn't happen if mapping is correct
        pass

    # QC: frameshift if CDS length not divisible by 3
    frameshift = (len(cds_dna) % 3 !=0)

    ambig = contains_ambiguous_bases(cds_dna)

    # Translation policy
    to_stop = (settings.STOP_POLICY == "truncate")
    protein = None
    prem_stop = False
    notes = None

    if cds_dna:
        try:
            protein = translate_dna(cds_dna, table=settings.GENETIC_CODE_TABLE, to_stop=to_stop,)

            # if policy keeps stops, detect internal stops:
            if settings.STOP_POLICY != "truncate" and "*" in protein:
                prem_stop = True
                notes = "Stop codon(s) present in translated protein."

            # if policy keeps truncation then detect proteins are truncated
            if settings.STOP_POLICY == "truncate":
                # if protein length is shorter than WT, then treat as premature stop
                if len(protein) < len(wt_mapping.wt_protein_aa):
                    prem_stop = True
                    notes = "Protein truncated due to in-frame stop codon."

        except Exception as e:
            protein = None
            notes = f"Translation failed: {type(e).__name__}: {e}"

    qc = QCFlags(
        has_ambiguous_bases=ambig,
        has_frameshift=frameshift,
        has_premature_stop=prem_stop,
        notes=notes,     
    )
    # Optional fallback gene finding if fast path is not working
    if fallback_search and (protein is None or frameshift):
        # TODO: implement fallback search by reusing map logic with wt_mapping.wt_protein_aa as target
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

def call_mutations_against_wt(
        wt_cds_dna: str,
        var_cds_dna: str,
        *,
        genetic_code_table: int,
) -> Tuple[List[MutationRecord], MutationCounts]:
    """
    Implent mutation calling and classification.
    Minimal substitutions handling:
    - compare codon by codon (zip over len//3)
    - classify synonymous vs nonsynonymous by translating codons
    Robust indel handling:
    - align proteins
    - map back to codons,
    - flag frameshifts/indels
    """
    # Substitutions only 
    muts: List[MutationRecord] = []
    syn = 0
    nonsyn = 0
    total = 0

    wt = normalise_dna(wt_cds_dna)
    var = normalise_dna(var_cds_dna)

    # if lengths fluctuate, flag as frameshift/indel 
    if len(wt) != len(var) or (len(wt) % 3 != 0) or (len(var) % 3 != 0):
        muts.append(
            MutationRecord(
                mutation_type="FRAMESHIFT",
                codon_index_1based=None,
                aa_position_1based=None,
                wt_codon=None,
                var_codon=None,
                wt_aa=None,
                var_aa=None,
                notes="CDS length mismatch or not divisible by 3; robust indel handling not implemented yet."
            )
        )
        return muts, MutationCounts(synonymous=0, nonsynonymous=0, total=1)

    codons = len(wt) // 3
    for i in range(codons):
        wt_codon = wt[i * 3 : i * 3 + 3]
        var_codon = var[i * 3 : i * 3 + 3]
        if wt_codon == var_codon:
            continue

        total += 1
        # if ambiguous codon, flag as ambiguous
        if any(b not in {"A", "C", "G", "T"} for b in set(var_codon)):
            muts.append(
                MutationRecord(
                    mutation_type="AMBIGUOUS",
                    codon_index_1based=i + 1,
                    aa_position_1based=i + 1,
                    wt_codon=wt_codon,
                    var_codon=var_codon,
                    wt_aa=None,
                    var_aa=None,
                    note="Ambiguous base(s) in variant codon."
                )
            )
            continue
        wt_aa = translate_dna(wt_codon, table=genetic_code_table, to_stop=False)
        var_aa = translate_dna(var_codon, table=genetic_code_table, to_stop=False)

        if var_aa == "*":
            mtype = "NONSENSE"
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
                note=None,
            )
        )

    return muts, MutationCounts(synonymous=syn, nonsynonymous=nonsyn, total=total)