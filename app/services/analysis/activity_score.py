"""Stage 4 activity-score calculations built from WT-normalized yields."""

import math
from typing import Dict, Tuple, List, Any
import pandas as pd

# Epsilon guard to prevent division-by-zero in normalised protein yield.
EPS = 1e-9


def compute_stage4_metrics(
    df_variants: pd.DataFrame,
    baselines: Dict[int, Tuple[float, float]],
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    """Compute WT-normalised activity scores and QC annotations for all variants.

    Each variant's raw DNA and protein yields are divided by the corresponding
    wild-type baseline for its generation.  The activity score is defined as
    ``dna_yield_norm / protein_yield_norm``.  Rows that fail any quality-control
    check are flagged but still included in the returned DataFrame.

    Args:
        df_variants: Must contain columns ``variant_id``, ``generation_id``,
            ``dna_yield_raw``, and ``protein_yield_raw``.
        baselines: Mapping of ``generation_id`` to ``(dna_wt, protein_wt)``
            wild-type average yields.

    Returns:
        A tuple of (rows_to_insert, df_out) where *rows_to_insert* is a list
        of metric dicts ready for database upsert and *df_out* is the input
        DataFrame augmented with normalised yields, activity scores, and a
        ``qc_stage4`` column indicating pass/fail reason.
    """

    required_cols = {"variant_id", "generation_id", "dna_yield_raw", "protein_yield_raw"}
    missing = required_cols - set(df_variants.columns)
    if missing:
        raise ValueError(f"Variant DF missing required columns: {missing}")

    qc_reasons: list[str] = []
    dna_norms: list[float] = []
    prot_norms: list[float] = []
    scores: list[float] = []

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

    # Build metric rows for DB upsert from QC-passing variants only.
    rows_to_insert: List[dict[str, Any]] = []
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

    return rows_to_insert, df_out
