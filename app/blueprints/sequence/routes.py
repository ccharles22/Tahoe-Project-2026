from __future__ import annotations

from flask import jsonify, request

from app.jobs.sequence.run_sequence_processing import run_sequence_processing
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
    wt_protein = acquire_uniprot_protein_fasta(accession)

    db_repo.save_staged_wt_protein(
        engine,
        experiment_id,
        accession,
        wt_protein,
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
    run_sequence_processing(experiment_id)
    return jsonify({"experiment_id": experiment_id, "status": "ANALYSIS_STARTED"}), 200


@sequence_bp.get("/health")
def health():
    return {"status": "ok"}, 200
