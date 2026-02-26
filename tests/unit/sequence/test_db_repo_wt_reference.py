"""Unit tests for WT reference loading from sequence DB repository."""

from unittest.mock import MagicMock

import pytest

from app.services.sequence.db_repo import get_wt_reference


def _mock_engine_with_row(row):
    engine = MagicMock()
    conn_ctx = MagicMock()
    conn = MagicMock()
    result = MagicMock()

    engine.connect.return_value = conn_ctx
    conn_ctx.__enter__.return_value = conn
    conn.execute.return_value = result
    result.fetchone.return_value = row
    return engine


def test_get_wt_reference_uses_experiment_plasmid_override_dict():
    engine = _mock_engine_with_row(("MKT", "ATGAAAACC", {"wt_plasmid_sequence": "TTTAAACCC"}))
    wt_protein, wt_plasmid = get_wt_reference(engine, experiment_id=1)
    assert wt_protein == "MKT"
    assert wt_plasmid == "TTTAAACCC"


def test_get_wt_reference_uses_experiment_plasmid_override_json_string():
    engine = _mock_engine_with_row(("MKT", "ATGAAAACC", '{"wt_plasmid_sequence":"gggcccaaa"}'))
    wt_protein, wt_plasmid = get_wt_reference(engine, experiment_id=1)
    assert wt_protein == "MKT"
    assert wt_plasmid == "GGGCCCAAA"


def test_get_wt_reference_falls_back_to_wt_plasmid():
    engine = _mock_engine_with_row(("MKT", "ATGAAAACC", {}))
    wt_protein, wt_plasmid = get_wt_reference(engine, experiment_id=1)
    assert wt_protein == "MKT"
    assert wt_plasmid == "ATGAAAACC"


def test_get_wt_reference_raises_on_missing_row():
    engine = _mock_engine_with_row(None)
    with pytest.raises(ValueError, match="No WT reference found"):
        get_wt_reference(engine, experiment_id=1)

