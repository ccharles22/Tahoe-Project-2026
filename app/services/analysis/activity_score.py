import math
from typing import Dict, Tuple, List, Any
import pandas as pd

EPS = 1e-9 #small constant to avoid division by zero in activity score calculation

def compute_stage4_metrics( #compute normalized DNA/protein yields and activity score, with QC checks; return rows to insert and full output dataframe
    df_variants: pd.DataFrame,
    baselines: Dict[int, Tuple[float, float]], #mapping from generation_id to (dna_wt, prot_wt) baselines for normalization
) -> tuple[list[dict[str, Any]], pd.DataFrame]: #returns list of rows to insert into metrics table and full output dataframe with QC results

    required_cols = {"variant_id", "generation_id", "dna_yield_raw", "protein_yield_raw"}
    missing = required_cols - set(df_variants.columns)
    if missing:
        raise ValueError(f"Variant DF missing required columns: {missing}")

    qc_reasons: list[str] = [] #list to track QC status for each variant, initialized empty and populated in loop
    dna_norms: list[float] = [] #list to store normalized DNA yields, initialized empty and populated in loop
    prot_norms: list[float] = [] #list to store normalized protein yields, initialized empty and populated in loop
    scores: list[float] = [] #list to store final activity scores, initialized empty and populated in loop

    for _, r in df_variants.iterrows():
        gen_id = int(r["generation_id"])
        dna_raw = r["dna_yield_raw"]
        prot_raw = r["protein_yield_raw"]

        # QC: must have raw metrics
        if pd.isna(dna_raw) or pd.isna(prot_raw):
            qc = "missing_raw_metrics"
            dna_norm = prot_norm = score = math.nan

        # QC: raw metrics must be positive
        elif float(dna_raw) <= 0 or float(prot_raw) <= 0:
            qc = "nonpositive_raw_metrics"
            dna_norm = prot_norm = score = math.nan

        # QC: must have WT baseline for this generation
        elif gen_id not in baselines:
            qc = "missing_wt_baseline"
            dna_norm = prot_norm = score = math.nan

        else:
            dna_wt, prot_wt = baselines[gen_id]

            # QC: baseline must be positive
            if dna_wt is None or prot_wt is None or dna_wt <= 0 or prot_wt <= 0:
                qc = "invalid_wt_baseline"
                dna_norm = prot_norm = score = math.nan
            else:
                dna_norm = float(dna_raw) / float(dna_wt)
                prot_norm = float(prot_raw) / float(prot_wt)

                # QC: avoid unstable division
                if prot_norm <= EPS:
                    qc = "protein_norm_too_small"
                    score = math.nan
                else:
                    qc = "ok"
                    score = dna_norm / prot_norm

        qc_reasons.append(qc)
        dna_norms.append(dna_norm)
        prot_norms.append(prot_norm)
        scores.append(score)

    df_out = df_variants.copy()
    df_out["dna_yield_norm"] = dna_norms
    df_out["protein_yield_norm"] = prot_norms
    df_out["activity_score"] = scores
    df_out["qc_stage4"] = qc_reasons

    df_valid = df_out[df_out["qc_stage4"] == "ok"].copy()

    rows_to_insert: List[dict[str, Any]] = [] #prepare list of rows to insert into metrics table for valid variants, with appropriate metric names, types, values, and units; invalid variants are skipped since their scores are not reliable
    for _, r in df_valid.iterrows():
        vid = int(r["variant_id"])
        gen_id = int(r["generation_id"])
        rows_to_insert.extend([
            {
                "generation_id": gen_id,
                "variant_id": vid,
                "wt_control_id": None,
                "metric_name": "dna_yield_norm",
                "metric_type": "normalized",
                "value": float(r["dna_yield_norm"]),
                "unit": "ratio",
                "metric_definition_id": None,
            },
            {
                "generation_id": gen_id,
                "variant_id": vid,
                "wt_control_id": None,
                "metric_name": "protein_yield_norm",
                "metric_type": "normalized",
                "value": float(r["protein_yield_norm"]),
                "unit": "ratio",
                "metric_definition_id": None,
            },
            {
                "generation_id": gen_id,
                "variant_id": vid,
                "wt_control_id": None,
                "metric_name": "activity_score",
                "metric_type": "derived",
                "value": float(r["activity_score"]),
                "unit": "ratio",
                "metric_definition_id": None,
            },
        ])

    return rows_to_insert, df_out #return the list of rows to insert into the metrics table for valid variants, along with the full output dataframe that includes QC results for all variants
