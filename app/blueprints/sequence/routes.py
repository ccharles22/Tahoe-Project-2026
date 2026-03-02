"""HTTP routes for WT staging and sequence-processing submission."""

from __future__ import annotations

from flask import jsonify, request

from app.jobs.run_sequence_processing import submit_sequence_processing
from app.services.sequence import db_repo
from app.services.sequence.db_repo import get_engine
from app.services.sequence.uniprot_service import acquire_uniprot_protein_fasta

from . import sequence_bp


@sequence_bp.post("/experiments/<int:experiment_id>/stage-wt")
def stage_wt(experiment_id: int):
    """Fetch and persist a staged UniProt WT protein for an experiment."""
    payload = request.get_json(force=True) or {}
    accession = payload.get("accession")

    if not accession:
        return jsonify({"error": "UniProt accession required"}), 400

    engine = get_engine()
    user_id, _ = db_repo.get_experiment_user_and_wt(engine, experiment_id)
    wt_protein = acquire_uniprot_protein_fasta(accession)

    db_repo.upsert_uniprot_staging(
        engine,
        experiment_id,
        user_id,
        accession,
        wt_protein,
        overwrite=True,
    )
    db_repo.clear_wt_mapping_cache(engine, experiment_id)

    return jsonify(
        {
            "experiment_id": experiment_id,
            "accession": accession,
            "protein_length": len(wt_protein),
            "status": "staged",
        }
    ), 200


@sequence_bp.post("/experiments/<int:experiment_id>/run")
def run_processing(experiment_id: int):
    """Submit sequence processing for the selected experiment."""
    engine = get_engine()
    payload = request.get_json(silent=True) or {}

    current_status = db_repo.get_experiment_status(engine, experiment_id)
    if current_status == "ANALYSIS_RUNNING":
        return jsonify(
            {
                "experiment_id": experiment_id,
                "status": current_status,
                "error": "Sequence processing is already running for this experiment.",
            }
        ), 409

    force_reprocess = bool(payload.get("force_reprocess", False))
    if db_repo.has_uniprot_staging(engine, experiment_id):
        force_reprocess = True

    submit_sequence_processing(experiment_id, force_reprocess=force_reprocess)
    return jsonify({"experiment_id": experiment_id, "status": "ANALYSIS_RUNNING"}), 202


@sequence_bp.get("/health")
def health():
    """Expose a lightweight health-check endpoint for the blueprint."""
    return {"status": "ok"}, 200
