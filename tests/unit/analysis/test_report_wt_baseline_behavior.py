import pandas as pd
import pytest

from app.services.analysis import report


class _DummyConnContext:
    def __enter__(self):
        return object()

    def __exit__(self, exc_type, exc, tb):
        return False


def test_report_main_raises_when_strict_wt_required_and_generation_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("EXPERIMENT_ID", "74")
    monkeypatch.setenv("STAGE4_REQUIRE_WT_BASELINE", "true")
    monkeypatch.setattr(report, "OUTPUT_DIR", str(tmp_path))

    monkeypatch.setattr(report, "get_conn", lambda: _DummyConnContext())
    monkeypatch.setattr(
        report,
        "fetch_variant_raw",
        lambda _conn, _eid: pd.DataFrame(
            [{"variant_id": 1, "generation_id": 100, "dna_yield_raw": 10.0, "protein_yield_raw": 5.0}]
        ),
    )
    monkeypatch.setattr(report, "fetch_wt_baselines", lambda _conn, _eid: ({100: (10.0, 5.0)}, [0]))

    with pytest.raises(RuntimeError, match=r"missing for generation\(s\): \[0\]"):
        report.main()


def test_report_main_keeps_wt_scoring_with_partial_baselines(monkeypatch, tmp_path):
    monkeypatch.setenv("EXPERIMENT_ID", "74")
    monkeypatch.delenv("STAGE4_REQUIRE_WT_BASELINE", raising=False)
    monkeypatch.setattr(report, "OUTPUT_DIR", str(tmp_path))

    monkeypatch.setattr(report, "get_conn", lambda: _DummyConnContext())
    monkeypatch.setattr(
        report,
        "fetch_variant_raw",
        lambda _conn, _eid: pd.DataFrame(
            [
                {"variant_id": 1, "generation_id": 100, "dna_yield_raw": 10.0, "protein_yield_raw": 5.0},
                {"variant_id": 2, "generation_id": 101, "dna_yield_raw": 9.0, "protein_yield_raw": 4.5},
            ]
        ),
    )
    monkeypatch.setattr(report, "fetch_wt_baselines", lambda _conn, _eid: ({100: (10.0, 5.0)}, [1]))

    fallback_called = {"value": False}
    wt_called = {"value": False}

    def fake_compute_stage4_metrics(df_variants, baselines):
        wt_called["value"] = True
        assert baselines == {100: (10.0, 5.0)}
        out = df_variants.copy()
        out["dna_yield_norm"] = [1.0, float("nan")]
        out["protein_yield_norm"] = [1.0, float("nan")]
        out["activity_score"] = [1.0, float("nan")]
        out["qc_stage4"] = ["ok", "missing_wt_baseline"]
        rows = [
            {
                "generation_id": 100,
                "variant_id": 1,
                "metric_name": "activity_score",
                "metric_type": "derived",
                "value": 1.0,
                "unit": "ratio",
            }
        ]
        return rows, out

    def fake_fallback(_df):
        fallback_called["value"] = True
        raise AssertionError("Fallback should not be used when partial WT baselines exist")

    monkeypatch.setattr(report, "compute_stage4_metrics", fake_compute_stage4_metrics)
    monkeypatch.setattr(report, "compute_activity_score_fallback", fake_fallback)
    monkeypatch.setattr(report, "upsert_variant_metrics", lambda _conn, rows: len(rows))

    monkeypatch.setattr(report, "fetch_top10", lambda _conn, _eid: pd.DataFrame())
    monkeypatch.setattr(report, "fetch_distribution", lambda _conn, _eid: pd.DataFrame())
    monkeypatch.setattr(report, "fetch_lineage_nodes", lambda _conn, _eid: pd.DataFrame())
    monkeypatch.setattr(report, "fetch_lineage_edges", lambda _conn, _eid: pd.DataFrame())

    report.main()

    assert wt_called["value"] is True
    assert fallback_called["value"] is False
