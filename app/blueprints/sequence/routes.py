from __future__ import annotations

from flask import jsonify, request

from app.jobs.run_sequence_processing import submit_sequence_processing
from app.services.sequence import db_repo
from app.services.sequence.db_repo import get_engine
from app.services.sequence.uniprot_service import acquire_uniprot_protein_fasta

from . import sequence_bp


@sequence_bp.post("/experiments/<int:experiment_id>/stage-wt")
def stage_wt(experiment_id: int):
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
    submit_sequence_processing(experiment_id, force_reprocess=False)
    return jsonify({"experiment_id": experiment_id, "status": "ANALYSIS_RUNNING"}), 202


@sequence_bp.get("/health")
def health():
    return {"status": "ok"}, 200
