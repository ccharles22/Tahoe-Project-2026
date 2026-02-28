"""Unit tests for sequence blueprint route behavior."""

from __future__ import annotations

from unittest.mock import patch

from flask import Flask


def _build_app() -> Flask:
    app = Flask(__name__)
    app.testing = True
    return app


def test_run_processing_rejects_duplicate_launch():
    from app.blueprints.sequence.routes import run_processing

    app = _build_app()
    engine = object()
    with app.test_request_context("/api/experiments/103/run", method="POST", json={}):
        with patch("app.blueprints.sequence.routes.get_engine", return_value=engine), \
             patch("app.blueprints.sequence.routes.db_repo.get_experiment_status", return_value="ANALYSIS_RUNNING"), \
             patch("app.blueprints.sequence.routes.submit_sequence_processing") as submit:
            response, status_code = run_processing(103)

    assert status_code == 409
    assert response.get_json()["status"] == "ANALYSIS_RUNNING"
    submit.assert_not_called()


def test_run_processing_forces_reprocess_when_staging_exists():
    from app.blueprints.sequence.routes import run_processing

    app = _build_app()
    engine = object()
    with app.test_request_context("/api/experiments/103/run", method="POST", json={}):
        with patch("app.blueprints.sequence.routes.get_engine", return_value=engine), \
             patch("app.blueprints.sequence.routes.db_repo.get_experiment_status", return_value="ANALYSED"), \
             patch("app.blueprints.sequence.routes.db_repo.has_uniprot_staging", return_value=True), \
             patch("app.blueprints.sequence.routes.submit_sequence_processing") as submit:
            response, status_code = run_processing(103)

    assert status_code == 202
    assert response.get_json()["status"] == "ANALYSIS_RUNNING"
    submit.assert_called_once_with(103, force_reprocess=True)


def test_run_processing_honours_explicit_force_reprocess():
    from app.blueprints.sequence.routes import run_processing

    app = _build_app()
    engine = object()
    with app.test_request_context(
        "/api/experiments/103/run",
        method="POST",
        json={"force_reprocess": True},
    ):
        with patch("app.blueprints.sequence.routes.get_engine", return_value=engine), \
             patch("app.blueprints.sequence.routes.db_repo.get_experiment_status", return_value="ANALYSED"), \
             patch("app.blueprints.sequence.routes.db_repo.has_uniprot_staging", return_value=False), \
             patch("app.blueprints.sequence.routes.submit_sequence_processing") as submit:
            response, status_code = run_processing(103)

    assert status_code == 202
    assert response.get_json()["status"] == "ANALYSIS_RUNNING"
    submit.assert_called_once_with(103, force_reprocess=True)


def test_stage_wt_clears_cached_wt_mapping():
    from app.blueprints.sequence.routes import stage_wt

    app = _build_app()
    engine = object()
    with app.test_request_context(
        "/api/experiments/103/stage-wt",
        method="POST",
        json={"accession": "P12345"},
    ):
        with patch("app.blueprints.sequence.routes.get_engine", return_value=engine), \
             patch("app.blueprints.sequence.routes.db_repo.get_experiment_user_and_wt", return_value=(7, 1)), \
             patch("app.blueprints.sequence.routes.acquire_uniprot_protein_fasta", return_value="MKT"), \
             patch("app.blueprints.sequence.routes.db_repo.upsert_uniprot_staging") as stage, \
             patch("app.blueprints.sequence.routes.db_repo.clear_wt_mapping_cache") as clear_cache:
            response, status_code = stage_wt(103)

    assert status_code == 200
    assert response.get_json()["protein_length"] == 3
    stage.assert_called_once_with(engine, 103, 7, "P12345", "MKT", overwrite=True)
    clear_cache.assert_called_once_with(engine, 103)
