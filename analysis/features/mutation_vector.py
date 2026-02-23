from __future__ import annotations

import pandas as pd


def build_mutation_matrix(mutations_df: pd.DataFrame) -> pd.DataFrame:
    """
    Binary presence/absence matrix of protein mutations for
    dimensionality reduction (PCA/t-SNE).

    Features are "{position}_{mutatedAA}" (e.g. "123_V").
    Rows = variant_id, columns = features, values = 0/1.
    """
    required = {"variant_id", "mutation_type", "position", "mutated"}
    missing = required - set(mutations_df.columns)
    if missing:
        raise ValueError(f"mutations_df missing required columns: {missing}")

    muts = mutations_df[mutations_df["mutation_type"] == "protein"].copy()
    if muts.empty:
        return pd.DataFrame()

    muts["feature"] = muts["position"].astype(str) + "_" + muts["mutated"].astype(str)
    muts["value"] = 1

    X = muts.pivot_table(
        index="variant_id",
        columns="feature",
        values="value",
        aggfunc="max",
        fill_value=0,
    )

    # Deterministic ordering improves reproducibility across runs
    X = X.reindex(sorted(X.columns), axis=1)
    X.index = X.index.astype(int)
    return X