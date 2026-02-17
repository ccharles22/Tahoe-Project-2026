from __future__ import annotations
from typing import Dict, Tuple, List, Any
import math
import pandas as pd

EPS = 1e-9  # small epsilon to avoid division by zero explosions

def compute_stage4_metrics(
    df_variants: pd.DataFrame,
    baselines: Dict[int, Tuple[float, float]],
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """
    Returns:
      rows_to_insert: list of dict rows for metrics insertion (variant_id, metric_name, metric_type, value, unit)
      df_valid: variant dataframe with computed columns (for debugging/plotting)
    """

    required_cols = {"variant_id", "generation_id", "dna_yield_raw", "protein_yield_raw"}
    missing = required_cols - set(df_variants.columns)
    if missing:
        raise ValueError(f"Variant DF missing required columns: {missing}")

    qc_reasons = []
    dna_norms = []
    prot_norms = []
    scores = []

    for _, r in df_variants.iterrows():
        variant_id = int(r["variant_id"])
        gen_id = int(r["generation_id"])

        dna_raw = r["dna_yield_raw"]
        prot_raw = r["protein_yield_raw"]

        # QC: must have raw metrics
        if pd.isna(dna_raw) or pd.isna(prot_raw):
            qc_reasons.append("missing_raw_metrics")
            dna_norms.append(math.nan)
            prot_norms.append(math.nan)
            scores.append(math.nan)
            continue

        # QC: must have WT baseline for this generation
        if gen_id not in baselines:
            qc_reasons.append("missing_wt_baseline")
            dna_norms.append(math.nan)
            prot_norms.append(math.nan)
            scores.append(math.nan)
            continue

        dna_wt, prot_wt = baselines[gen_id]

        # QC: baseline must be positive
        if dna_wt is None or prot_wt is None or dna_wt <= 0 or prot_wt <= 0:
            qc_reasons.append("invalid_wt_baseline")
            dna_norms.append(math.nan)
            prot_norms.append(math.nan)
            scores.append(math.nan)
            continue

        dna_norm = float(dna_raw) / float(dna_wt)
        prot_norm = float(prot_raw) / float(prot_wt)

        # QC: protein norm must not be ~0
        if prot_norm <= EPS:
            qc_reasons.append("protein_norm_too_small")
            dna_norms.append(dna_norm)
            prot_norms.append(prot_norm)
            scores.append(math.nan)
            continue

        score = dna_norm / prot_norm

        qc_reasons.append("ok")
        dna_norms.append(dna_norm)
        prot_norms.append(prot_norm)
        scores.append(score)

    df_out = df_variants.copy()
    df_out["dna_yield_norm"] = dna_norms
    df_out["protein_yield_norm"] = prot_norms
    df_out["activity_score"] = scores
    df_out["qc_stage4"] = qc_reasons

    # only insert rows where score is valid and qc ok
    df_valid = df_out[df_out["qc_stage4"] == "ok"].copy()

    rows_to_insert: List[dict] = []
    for _, r in df_valid.iterrows():
        vid = int(r["variant_id"])
        gid = int(r["generation_id"])
        rows_to_insert.append({"generation_id": gid, "variant_id": vid, "metric_name": "dna_yield_norm", "metric_type": "normalized", "value": float(r["dna_yield_norm"]), "unit": "ratio"})
        rows_to_insert.append({"generation_id": gid, "variant_id": vid, "metric_name": "protein_yield_norm", "metric_type": "normalized", "value": float(r["protein_yield_norm"]), "unit": "ratio"})
        rows_to_insert.append({"generation_id": gid, "variant_id": vid, "metric_name": "activity_score", "metric_type": "derived", "value": float(r["activity_score"]), "unit": "ratio"})

    return rows_to_insert, df_out