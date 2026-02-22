import math

import pandas as pd

from app.services.analysis.activity_score import compute_stage4_metrics


def test_compute_stage4_metrics_happy_path_creates_three_rows_per_variant():
	df = pd.DataFrame(
		[
			{
				"variant_id": 1,
				"generation_id": 10,
				"dna_yield_raw": 20.0,
				"protein_yield_raw": 4.0,
			}
		]
	)
	baselines = {10: (10.0, 2.0)}

	rows_to_insert, df_out = compute_stage4_metrics(df, baselines)

	assert len(rows_to_insert) == 3
	assert set(df_out["qc_stage4"].unique()) == {"ok"}
	assert math.isclose(float(df_out.loc[0, "dna_yield_norm"]), 2.0)
	assert math.isclose(float(df_out.loc[0, "protein_yield_norm"]), 2.0)
	assert math.isclose(float(df_out.loc[0, "activity_score"]), 1.0)


def test_compute_stage4_metrics_marks_missing_baseline():
	df = pd.DataFrame(
		[
			{
				"variant_id": 2,
				"generation_id": 99,
				"dna_yield_raw": 5.0,
				"protein_yield_raw": 5.0,
			}
		]
	)

	rows_to_insert, df_out = compute_stage4_metrics(df, baselines={})

	assert rows_to_insert == []
	assert df_out.loc[0, "qc_stage4"] == "missing_wt_baseline"
	assert pd.isna(df_out.loc[0, "activity_score"])
