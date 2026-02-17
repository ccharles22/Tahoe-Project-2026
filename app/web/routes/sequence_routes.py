from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.services import db_repo
from app.services.db_repo import get_engine
from app.services.uniprot_service import acquire_uniprot_protein_fasta

bp = Blueprint("sequence", __name__)


@bp.post("/experiments/<int:experiment_id>/stage-wt")
def stage_wt(experiment_id: int):
    """
    Retrieves WT protein from UniProt and stages it in the database.
    """

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
    )

    return jsonify(
        {
        "experiment_id": experiment_id,
        "accession": accession,
        "protein_length": len(wt_protein),
        "status": "staged"
    }
), 200


@bp.post("/experiments/<int:experiment_id>/run")
def run_processing(experiment_id: int):
    """
    Triggers the full sequence processing pipeline for the specified experiment.
        """
    from app.jobs.run_sequence_processing import run_sequence_processing
    run_sequence_processing(experiment_id)

    return jsonify({
        "experiment_id": experiment_id,
        "status": "ANALYSIS_STARTED"
    }), 200

@bp.get("health")
def health():
    return {"status": "ok"}, 200