import numpy as np
import pandas as pd

from app.services.analysis import queries


def test_fetch_wt_baselines_returns_available_and_missing_generation_numbers(monkeypatch):
    wt_df = pd.DataFrame(
        [
            {"generation_id": 100, "dna_wt": 10.0, "prot_wt": 5.0},
            {"generation_id": 101, "dna_wt": 12.0, "prot_wt": np.nan},
            {"generation_id": 102, "dna_wt": 8.0, "prot_wt": 4.0},
        ]
    )
    generations_df = pd.DataFrame(
        [
            {"generation_id": 100, "generation_number": 0},
            {"generation_id": 101, "generation_number": 1},
            {"generation_id": 102, "generation_number": 2},
        ]
    )

    calls = {"n": 0}

    def fake_read_sql(_sql, _conn, params=None):
        calls["n"] += 1
        if calls["n"] == 1:
            assert params == (74,)
            return wt_df
        if calls["n"] == 2:
            assert params == (74,)
            return generations_df
        raise AssertionError("Unexpected extra read_sql call")

    monkeypatch.setattr(queries.pd, "read_sql", fake_read_sql)

    baselines, missing_generations = queries.fetch_wt_baselines(conn=object(), experiment_id=74)

    assert baselines == {
        100: (10.0, 5.0),
        102: (8.0, 4.0),
    }
    assert missing_generations == [1]
