"""Fallback scoring logic used when WT controls are unavailable."""

import numpy as np
import pandas as pd

def compute_activity_score_fallback(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Compute WT-free activity scores using per-generation median normalisation.

    Within each generation, DNA and protein yields are divided by their
    respective medians.  The activity score is then ``dna_rel / prot_rel``.

    Args:
        df_raw: Must contain ``variant_id``, ``generation_id``,
            ``dna_yield_raw``, and ``protein_yield_raw``.

    Returns:
        A DataFrame with columns ``variant_id``, ``generation_id``,
        ``dna_yield_norm``, ``protein_yield_norm``, and ``activity_score``.
        Rows with non-finite scores are dropped.
    """

    # Work on a copy to keep caller data unchanged.
    d = df_raw.copy()

    # Ensure numeric
    d["dna_yield_raw"] = pd.to_numeric(d["dna_yield_raw"], errors="coerce")
    d["protein_yield_raw"] = pd.to_numeric(d["protein_yield_raw"], errors="coerce")
    d = d.dropna(subset=["dna_yield_raw", "protein_yield_raw"])

    # Within-generation medians
    d["dna_med"] = d.groupby("generation_id")["dna_yield_raw"].transform("median")
    d["prot_med"] = d.groupby("generation_id")["protein_yield_raw"].transform("median")

    # Avoid divide-by-zero
    d["dna_med"] = d["dna_med"].replace(0, np.nan)
    d["prot_med"] = d["prot_med"].replace(0, np.nan)

    d["dna_yield_norm"] = d["dna_yield_raw"] / d["dna_med"]
    d["protein_yield_norm"] = d["protein_yield_raw"] / d["prot_med"]

    # Higher score means DNA signal is strong relative to protein within generation-normalized space.
    d["activity_score"] = d["dna_yield_norm"] / d["protein_yield_norm"]

    # Clean up infinities/nans
    d = d.replace([np.inf, -np.inf], np.nan).dropna(subset=["activity_score"])

    # Return only fields expected downstream by DB upsert/report layers.
    return d[["variant_id", "generation_id", "dna_yield_norm", "protein_yield_norm", "activity_score"]]
