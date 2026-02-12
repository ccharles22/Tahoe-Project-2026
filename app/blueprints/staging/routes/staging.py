import json
import os
from flask import jsonify, render_template, request, redirect, url_for, Response, current_app
from uuid import uuid4
from app.services.staging.parse_fasta import parse_fasta
from app.models import Experiment, WildtypeProtein, Plasmid, StagingValidation
from app.extensions import db
from app.services.staging.uniprot_service import UniprotService, UniprotServiceError
from app.services.staging.plasmid_validator import validate_plasmid
from app.services.staging.backtranslate import backtranslate
from app.services.analysis import report

from .. import staging_bp

# Route to create or view an experiment
@staging_bp.get('/')
def create_experiment():
    experiment_id = request.args.get('experiment_id', '').strip()
    accession = request.args.get('accession', '').strip()
    wt_message = request.args.get('wt_message', '').strip()
    analysis_message = request.args.get('analysis_message', '').strip()

    analysis_outputs = {}

    wt = None
    validation = None

    if experiment_id.isdigit():
        exp_id_int = int(experiment_id)
        wt = WildtypeProtein.query.filter_by(experiment_id=exp_id_int).first()
        validation = StagingValidation.query.filter_by(experiment_id=exp_id_int).first()

        gen_dir = os.path.join(current_app.root_path, "static", "generated")
        plot_path = os.path.join(gen_dir, "activity_distribution.png")
        top10_path = os.path.join(gen_dir, "top10_variants.csv")
        qc_path = os.path.join(gen_dir, "stage4_qc_debug.csv")

        analysis_outputs = {
            "plot": {
                "path": plot_path,
                "url": url_for("static", filename="generated/activity_distribution.png"),
                "label": "Activity distribution plot",
                "exists": os.path.exists(plot_path),
            },
            "top10": {
                "path": top10_path,
                "url": url_for("static", filename="generated/top10_variants.csv"),
                "label": "Top 10 variants (CSV)",
                "exists": os.path.exists(top10_path),
            },
            "qc": {
                "path": qc_path,
                "url": url_for("static", filename="generated/stage4_qc_debug.csv"),
                "label": "Stage 4 QC debug (CSV)",
                "exists": os.path.exists(qc_path),
            },
        }

    return render_template(
        "staging/create_experiment.html",
        experiment_id=experiment_id,
        wt=wt,
        validation=validation,
        wt_message=wt_message,
        analysis_message=analysis_message,
        analysis_outputs=analysis_outputs
    )


@staging_bp.post('/analysis/run')
def run_analysis():
    experiment_id = request.form.get('experiment_id', '').strip()
    if not experiment_id.isdigit():
        return redirect(url_for('staging.create_experiment', analysis_message='Missing experiment_id.'))

    exp_id_int = int(experiment_id)
    prev_env = os.getenv("EXPERIMENT_ID")
    os.environ["EXPERIMENT_ID"] = str(exp_id_int)

    try:
        report.main()
        message = "Analysis completed. Results are available below."
    except Exception as exc:
        message = f"Analysis failed: {exc}"
    finally:
        if prev_env is None:
            os.environ.pop("EXPERIMENT_ID", None)
        else:
            os.environ["EXPERIMENT_ID"] = prev_env

    return redirect(url_for('staging.create_experiment', experiment_id=experiment_id, analysis_message=message))

# Route to handle UniProt accession submission  
@staging_bp.post('/uniprot')
def fetch_uniprot():
    accession = request.form.get('accession', '').strip()
    if not accession:
        return redirect(url_for('staging.create_experiment', wt_message='Missing accession'))

    # 1) create experiment
    exp = Experiment(status='WT_FETCHING')
    db.session.add(exp)
    db.session.commit()  # exp.id now exists

    # 2) create WT row (stub for now; later fill with UniProtService)
    wt = WildtypeProtein(
        experiment_id=exp.id,
        uniprot_accession=accession,
        wt_protein_sequence=None,
        features_json=None,
        protein_length=None,
        plasmid_length=None
    )
    db.session.add(wt)
    db.session.commit()

    try:
        result = UniprotService.fetch(accession)
    except UniprotServiceError as e:
        exp.status = "WT_FAILED"
        db.session.commit()
        return redirect(url_for(
            "staging.create_experiment",
            experiment_id=str(exp.id),
            wt_message=str(e)
        ))

    # save WT results
    wt.wt_protein_sequence = result["sequence"]
    wt.protein_length = result["protein_length"]
    wt.features_json = json.dumps(result["features"])
    exp.status = "WT_FETCHED"
    db.session.commit()

    return redirect(url_for(
        'staging.create_experiment',
        experiment_id=str(exp.id),
        wt_message=f'Fetched WT sequence + features successfully.'
    ))

# Route to handle plasmid FASTA upload and validation
@staging_bp.post('/plasmid')
def upload_plasmid():
    experiment_id = request.form.get('experiment_id', '').strip()
    file = request.files.get('plasmid_fasta')

    if not experiment_id.isdigit():
        return redirect(url_for('staging.create_experiment', wt_message='Invalid experiment_id'))

    exp_id_int = int(experiment_id)

    wt = WildtypeProtein.query.filter_by(experiment_id=exp_id_int).first()
    if not wt:
        return redirect(url_for('staging.create_experiment', wt_message='Unknown experiment_id. Fetch WT first.'))

    if not file:
        return redirect(url_for('staging.create_experiment', experiment_id=experiment_id, wt_message='No file uploaded'))

    try:
        dna = parse_fasta(file.read())
    except ValueError as e:
        return redirect(url_for('staging.create_experiment', experiment_id=experiment_id, wt_message=str(e)))

    plasmid = Plasmid.query.filter_by(experiment_id=exp_id_int).first()
    if plasmid:
        plasmid.dna_sequence = dna
    else:
        plasmid = Plasmid(experiment_id=exp_id_int, dna_sequence=dna)
        db.session.add(plasmid)

    wt.plasmid_length = len(dna)

    # --- REAL validation (exact match v1) ---
    if not wt.wt_protein_sequence:
        return redirect(url_for(
            'staging.create_experiment',
            experiment_id=experiment_id,
            wt_message='WT protein sequence missing. Fetch WT again.'
        ))

    result = validate_plasmid(wt.wt_protein_sequence, dna)

    val = StagingValidation.query.filter_by(experiment_id=exp_id_int).first()
    if not val:
        val = StagingValidation(experiment_id=exp_id_int)
        db.session.add(val)

    val.is_valid = result.is_valid
    val.identity = result.identity
    val.coverage = result.coverage
    val.strand = result.strand
    val.start_nt = result.start_nt
    val.end_nt = result.end_nt
    val.wraps = result.wraps
    val.message = result.message
    
    exp = Experiment.query.filter_by(id=exp_id_int).first()
    if exp:
        exp.status = 'STAGED_VALID' if result.is_valid else 'STAGED_INVALID'

    # --- end validation ---

    db.session.commit()

    return redirect(url_for(
        'staging.create_experiment',
        experiment_id=experiment_id,
        wt_message='Plasmid validated.' if result.is_valid else 'Plasmid invalid (see details).'
    ))

# Route to download the backtranslated plasmid FASTA
@staging_bp.get('/dev/plasmid_fasta/<int:experiment_id>')
def dev_plasmid_fasta(experiment_id: int):
    wt = WildtypeProtein.query.filter_by(experiment_id=experiment_id).first()
    if not wt or not wt.wt_protein_sequence:
        return Response("WT protein sequence not found for this experiment.", status=404)
    
    dna = backtranslate(wt.wt_protein_sequence)

    fasta = f">dev_plasmid_experiment_{experiment_id}\n"
    # wrap fasta lines
    for i in range(0, len(dna), 70):
        fasta += dna[i:i+70] + "\n"

    resp = Response(fasta, mimetype='application/x-fasta')
    resp.headers['Content-Disposition'] = f'attachment; filename=dev_plasmid_experiment_{experiment_id}.fasta'
    return resp
