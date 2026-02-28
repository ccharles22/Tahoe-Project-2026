"""Unit tests for WT reference loading from the sequence repository."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from app.services.sequence.db_repo import get_wt_reference


def _mock_engine(sequence_row, staged_row=None):
    engine = MagicMock()
    conn_ctx = MagicMock()
    conn = MagicMock()

    engine.connect.return_value = conn_ctx
    conn_ctx.__enter__.return_value = conn

    seq_result = MagicMock()
    seq_result.fetchone.return_value = sequence_row

    staged_result = MagicMock()
    staged_result.fetchone.return_value = staged_row

    conn.execute.side_effect = [seq_result, staged_result]
    return engine


def test_get_wt_reference_uses_experiment_wt_when_no_staging():
    engine = _mock_engine(("MKT", "ATGAAAACC"), None)

    wt_protein, wt_plasmid = get_wt_reference(engine, experiment_id=1)

    assert wt_protein == "MKT"
    assert wt_plasmid == "ATGAAAACC"


def test_get_wt_reference_uses_staged_protein_override():
    payload = json.dumps(
        {
            "user_id": 7,
            "accession": "P12345",
            "protein_sequence": "mktaa",
        }
    )
    engine = _mock_engine(("MKT", "ATGAAAACC"), (payload,))

    wt_protein, wt_plasmid = get_wt_reference(engine, experiment_id=1)

    assert wt_protein == "MKTAA"
    assert wt_plasmid == "ATGAAAACC"


def test_get_wt_reference_ignores_invalid_staging_payload():
    engine = _mock_engine(("MKT", "ATGAAAACC"), ("not-json",))

    wt_protein, wt_plasmid = get_wt_reference(engine, experiment_id=1)

    assert wt_protein == "MKT"
    assert wt_plasmid == "ATGAAAACC"


def test_get_wt_reference_raises_on_missing_row():
    engine = _mock_engine(None, None)

    with pytest.raises(ValueError, match="No WT reference found"):
        get_wt_reference(engine, experiment_id=1)
