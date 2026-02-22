from __future__ import annotations

import os
import json
import pandas as pd

from app.services.analysis.database import get_conn


# Map dataset columns -> your metric names
DNA_COL = "DNA_Quantification_fg"
PROT_COL = "Protein_Quantification_pg"
GEN_COL = "Directed_Evolution_Generation"
IDX_COL = "Plasmid_Variant_Index"
PARENT_COL = "Parent_Plasmid_Variant"
SEQ_COL = "Assembled_DNA_Sequence"
CONTROL_COL = "Control"


def load_table(path: str) -> pd.DataFrame:
    if path.endswith(".tsv"):
        return pd.read_csv(path, sep="\t")
    if path.endswith(".json"):
        with open(path, "r") as f:
            data = json.load(f)
        return pd.DataFrame(data)
    raise ValueError("Unsupported file type (use .tsv or .json)")


def ensure_generation(cur, experiment_id: int, generation_number: int) -> int:
    cur.execute(
        """
        INSERT INTO generations (experiment_id, generation_number)
        VALUES (%s, %s)
        ON CONFLICT (experiment_id, generation_number) DO UPDATE
        SET generation_number = EXCLUDED.generation_number
        RETURNING generation_id;
        """,
        (experiment_id, generation_number),
    )
    return int(cur.fetchone()[0])


def get_experiment_wt_id(cur, experiment_id: int) -> int:
    cur.execute("SELECT wt_id FROM experiments WHERE experiment_id = %s;", (experiment_id,))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Experiment {experiment_id} not found in experiments table.")
    return int(row[0])


def ensure_wt_control(cur, generation_id: int, wt_id: int) -> int:
    cur.execute(
        """
        INSERT INTO wild_type_controls (generation_id, wt_id)
        VALUES (%s, %s)
        ON CONFLICT (generation_id, wt_id) DO UPDATE
        SET wt_id = EXCLUDED.wt_id
        RETURNING wt_control_id;
        """,
        (generation_id, wt_id),
    )
    return int(cur.fetchone()[0])


def upsert_metric_for_wt(cur, wt_control_id: int, name: str, value: float, unit: str = "") -> None:
    cur.execute(
        """
        INSERT INTO metrics (wt_control_id, metric_name, metric_type, value, unit)
        VALUES (%s, %s, 'raw', %s, %s)
        ON CONFLICT (generation_id, wt_control_id, metric_name, metric_type)
        WHERE wt_control_id IS NOT NULL
        DO UPDATE SET value = EXCLUDED.value, unit = EXCLUDED.unit;
        """,
        (wt_control_id, name, float(value), unit),
    )


def ensure_variant(cur, generation_id: int, plasmid_variant_index: int, parent_variant_id: int | None, dna_seq: str | None) -> int:
    # Your schema uses plasmid_variant_index as varchar, so cast to str
    cur.execute(
        """
        INSERT INTO variants (generation_id, parent_variant_id, plasmid_variant_index, assembled_dna_sequence)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (generation_id, plasmid_variant_index) DO UPDATE
        SET
          assembled_dna_sequence = COALESCE(EXCLUDED.assembled_dna_sequence, variants.assembled_dna_sequence)
        RETURNING variant_id;
        """,
        (generation_id, parent_variant_id, str(plasmid_variant_index), dna_seq),
    )
    return int(cur.fetchone()[0])


def _norm_index(value) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        as_num = float(text)
        if as_num.is_integer():
            return str(int(as_num))
    except ValueError:
        pass
    return text


def resolve_parent_variant_id(
    *,
    child_generation: int,
    parent_index: str | None,
    ids_by_generation_and_index: dict[tuple[int, str], int],
) -> int | None:
    if parent_index is None:
        return None

    # Preferred interpretation: parent index belongs to previous generation.
    candidate = ids_by_generation_and_index.get((child_generation - 1, parent_index))
    if candidate is not None:
        return candidate

    return None


def purge_experiment_variants(cur, experiment_id: int) -> tuple[int, int]:
    cur.execute(
        """
        SELECT v.variant_id
        FROM variants v
        JOIN generations g ON g.generation_id = v.generation_id
        WHERE g.experiment_id = %s;
        """,
        (experiment_id,),
    )
    variant_ids = [int(r[0]) for r in cur.fetchall()]
    if not variant_ids:
        return 0, 0

    cur.execute("DELETE FROM metrics WHERE variant_id = ANY(%s);", (variant_ids,))
    deleted_metrics = cur.rowcount

    cur.execute("DELETE FROM variants WHERE variant_id = ANY(%s);", (variant_ids,))
    deleted_variants = cur.rowcount

    return deleted_variants, deleted_metrics


def upsert_metric_for_variant(cur, variant_id: int, name: str, value: float, unit: str = "") -> None:
    cur.execute(
        """
        INSERT INTO metrics (variant_id, metric_name, metric_type, value, unit)
        VALUES (%s, %s, 'raw', %s, %s)
        ON CONFLICT (generation_id, variant_id, metric_name, metric_type)
        WHERE variant_id IS NOT NULL
        DO UPDATE SET value = EXCLUDED.value, unit = EXCLUDED.unit;
        """,
        (variant_id, name, float(value), unit),
    )


def main() -> None:
    dataset_path = os.getenv("DATASET_PATH", "")
    experiment_id = int(os.getenv("EXPERIMENT_ID", "1"))
    reset_variants = os.getenv("RESET_EXPERIMENT_VARIANTS", "0").strip().lower() in {"1", "true", "yes"}

    if not dataset_path:
        raise RuntimeError("Set DATASET_PATH to the .tsv or .json file you want to load.")

    df = load_table(dataset_path)

    # Basic QC: required columns exist
    required = {IDX_COL, GEN_COL, DNA_COL, PROT_COL, CONTROL_COL}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Dataset missing columns: {missing}")

    with get_conn() as conn:
        with conn.cursor() as cur:
            if reset_variants:
                deleted_variants, deleted_metrics = purge_experiment_variants(cur, experiment_id)
                print(f"[Reset] Deleted {deleted_variants} variants and {deleted_metrics} variant metrics for experiment {experiment_id}.")

            wt_id = get_experiment_wt_id(cur, experiment_id)

            # 1) Ensure generations exist
            gen_map: dict[int, int] = {}
            for gen_num in sorted(df[GEN_COL].dropna().unique()):
                gen_id = ensure_generation(cur, experiment_id, int(gen_num))
                gen_map[int(gen_num)] = gen_id

            # 2) WT baselines per generation (mean of Control==True)
            wt_df = df[df[CONTROL_COL] == True].copy()
            if wt_df.empty:
                raise ValueError("No WT control rows found (Control==true). Cannot create WT baselines.")

            wt_means = (
                wt_df.groupby(GEN_COL)[[DNA_COL, PROT_COL]]
                .mean(numeric_only=True)
                .reset_index()
            )

            for _, r in wt_means.iterrows():
                gen_num = int(r[GEN_COL])
                gen_id = gen_map[gen_num]

                wt_control_id = ensure_wt_control(cur, gen_id, wt_id)

                upsert_metric_for_wt(cur, wt_control_id, "dna_yield_raw", float(r[DNA_COL]), "fg")
                upsert_metric_for_wt(cur, wt_control_id, "protein_yield_raw", float(r[PROT_COL]), "pg")

            # 3) Insert variants + their raw metrics (Control==False)
            var_df = df[df[CONTROL_COL] == False].copy()

            # Keep order deterministic (helps parent resolution on repeated loads)
            var_df["_gen_num"] = pd.to_numeric(var_df[GEN_COL], errors="coerce")
            if IDX_COL in var_df.columns:
                var_df["_idx_num"] = pd.to_numeric(var_df[IDX_COL], errors="coerce")
            else:
                var_df["_idx_num"] = pd.NA
            var_df = var_df.sort_values(["_gen_num", "_idx_num"], kind="mergesort")

            # Single pass: resolve parent from previous generation, then insert.
            ids_by_generation_and_index: dict[tuple[int, str], int] = {}

            for _, r in var_df.iterrows():
                gen_num = int(r[GEN_COL])
                gen_id = gen_map[gen_num]

                plasmid_idx = _norm_index(r[IDX_COL])
                if plasmid_idx is None:
                    continue

                parent_idx = _norm_index(r.get(PARENT_COL)) if PARENT_COL in df.columns else None
                dna_seq = r.get(SEQ_COL) if SEQ_COL in df.columns else None
                parent_variant_id = resolve_parent_variant_id(
                    child_generation=gen_num,
                    parent_index=parent_idx,
                    ids_by_generation_and_index=ids_by_generation_and_index,
                )

                variant_id = ensure_variant(cur, gen_id, plasmid_idx, parent_variant_id, dna_seq)
                ids_by_generation_and_index[(gen_num, plasmid_idx)] = variant_id

                upsert_metric_for_variant(cur, variant_id, "dna_yield_raw", float(r[DNA_COL]), "fg")
                upsert_metric_for_variant(cur, variant_id, "protein_yield_raw", float(r[PROT_COL]), "pg")

        conn.commit()

    print("Loaded WT baselines + variant raw metrics successfully.")
    print("Now run: python -m scripts.run_report")


if __name__ == "__main__":
    main()
