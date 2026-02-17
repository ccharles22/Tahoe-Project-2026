import json
import os
from flask import jsonify, render_template, request, redirect, url_for, Response, current_app
from uuid import uuid4
from sqlalchemy.exc import SQLAlchemyError
from app.services.staging.parse_fasta import parse_fasta
from app.models import Experiment, WildtypeProtein, Plasmid, StagingValidation
from app.extensions import db
from app.services.staging.uniprot_service import UniprotService, UniprotServiceError
from app.services.staging.plasmid_validator import validate_plasmid
from app.services.staging.backtranslate import backtranslate
from app.services.analysis import report
from app.jobs.run_sequence_processing import run_sequence_processing
from sqlalchemy.exc import SQLAlchemyError

from .. import staging_bp

# Route to create or view an experiment
@staging_bp.get('/')
def create_experiment():
    experiment_id = request.args.get('experiment_id', '').strip()
    accession = request.args.get('accession', '').strip()
    wt_message = request.args.get('wt_message', '').strip()
    analysis_message = request.args.get('analysis_message', '').strip()
    sequence_message = request.args.get('sequence_message', '').strip()

    analysis_outputs = {}

    wt = None
    validation = None

    if experiment_id.isdigit():
        exp_id_int = int(experiment_id)
        try:
            wt = WildtypeProtein.query.filter_by(experiment_id=exp_id_int).first()
            validation = StagingValidation.query.filter_by(experiment_id=exp_id_int).first()
        except SQLAlchemyError:
            db.session.rollback()
            wt = None
            validation = None

        gen_dir = os.path.join(current_app.root_path, "static", "generated")
        plot_filename = f"activity_distribution_exp_{exp_id_int}.png"
        top10_filename = f"top10_variants_exp_{exp_id_int}.csv"
        qc_filename = f"stage4_qc_debug_exp_{exp_id_int}.csv"

        plot_path = os.path.join(gen_dir, plot_filename)
        top10_path = os.path.join(gen_dir, top10_filename)
        qc_path = os.path.join(gen_dir, qc_filename)

        analysis_outputs = {
            "plot": {
                "path": plot_path,
                "url": url_for("static", filename=f"generated/{plot_filename}"),
                "label": "Activity distribution plot",
                "exists": os.path.exists(plot_path),
            },
            "top10": {
                "path": top10_path,
                "url": url_for("static", filename=f"generated/{top10_filename}"),
                "label": "Top 10 variants (CSV)",
                "exists": os.path.exists(top10_path),
            },
            "qc": {
                "path": qc_path,
                "url": url_for("static", filename=f"generated/{qc_filename}"),
                "label": "Stage 4 QC debug (CSV)",
                "exists": os.path.exists(qc_path),
            },
        }

    # Fetch all experiments to display in sidebar, ordered by most recent first
    all_experiments = Experiment.query.order_by(Experiment.created_at.desc()).limit(10).all()

    return render_template(
        "staging/create_experiment.html",
        experiment_id=experiment_id,
        wt=wt,
        validation=validation,
        wt_message=wt_message,
        analysis_message=analysis_message,
        analysis_outputs=analysis_outputs,
        sequence_message=sequence_message,
        all_experiments=all_experiments,
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


@staging_bp.post('/sequence/run')
def run_sequence():
    experiment_id = request.form.get('experiment_id', '').strip()
    if not experiment_id.isdigit():
        return redirect(url_for('staging.create_experiment', sequence_message='Missing experiment_id.'))

    try:
        run_sequence_processing(int(experiment_id))
        message = "Sequence processing completed. Outputs are stored in the database."
    except Exception as exc:
        message = f"Sequence processing failed: {exc}"

    return redirect(url_for('staging.create_experiment', experiment_id=experiment_id, sequence_message=message))

# Route to create a new blank experiment
@staging_bp.post('/experiment/new')
def create_new_experiment():
    """Create a blank experiment without requiring UniProt accession"""
    from flask_login import current_user
    from datetime import datetime
    
    # Generate a default name with timestamp
    default_name = f"Experiment {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    # Create new experiment with initial status
    exp = Experiment(
        name=default_name,
        user_id=current_user.user_id if current_user.is_authenticated else 1,  # Default to user 1 if not logged in
        wt_id=0  # Placeholder, will be updated when WT is fetched
    )
    db.session.add(exp)
    db.session.commit()

    # Redirect to the experiment page
    return redirect(url_for('staging.create_experiment', experiment_id=str(exp.experiment_id)))


@staging_bp.post('/experiment/rename')
def rename_experiment():
    experiment_id = request.form.get('experiment_id', '').strip()
    current_experiment_id = request.form.get('current_experiment_id', '').strip()
    new_name = request.form.get('name', '').strip()

    if not experiment_id.isdigit():
        target = current_experiment_id if current_experiment_id.isdigit() else ''
        return redirect(url_for('staging.create_experiment', experiment_id=target))

    if not new_name:
        target = current_experiment_id if current_experiment_id.isdigit() else experiment_id
        return redirect(url_for('staging.create_experiment', experiment_id=target, wt_message='Experiment name cannot be empty.'))

    exp_id_int = int(experiment_id)
    exp = Experiment.query.filter_by(experiment_id=exp_id_int).first()
    if not exp:
        target = current_experiment_id if current_experiment_id.isdigit() else ''
        return redirect(url_for('staging.create_experiment', experiment_id=target, wt_message='Experiment not found.'))

    exp.name = new_name[:255]
    db.session.commit()

    target = current_experiment_id if current_experiment_id.isdigit() else experiment_id
    return redirect(url_for('staging.create_experiment', experiment_id=target))


@staging_bp.post('/experiment/delete')
def delete_experiment():
    experiment_id = request.form.get('experiment_id', '').strip()
    current_experiment_id = request.form.get('current_experiment_id', '').strip()

    def _redirect_to(target_id: str = '', message: str = ''):
        if target_id and target_id.isdigit():
            if message:
                return redirect(url_for('staging.create_experiment', experiment_id=target_id, wt_message=message))
            return redirect(url_for('staging.create_experiment', experiment_id=target_id))
        if message:
            return redirect(url_for('staging.create_experiment', wt_message=message))
        return redirect(url_for('staging.create_experiment'))

    if not experiment_id.isdigit():
        target = current_experiment_id if current_experiment_id.isdigit() else ''
        return _redirect_to(target, 'Invalid experiment id.')

    exp_id_int = int(experiment_id)
    exp = Experiment.query.filter_by(experiment_id=exp_id_int).first()
    if not exp:
        target = current_experiment_id if current_experiment_id.isdigit() else ''
        return _redirect_to(target, 'Experiment not found.')

    try:
        StagingValidation.query.filter_by(experiment_id=exp_id_int).delete()
        Plasmid.query.filter_by(experiment_id=exp_id_int).delete()
        WildtypeProtein.query.filter_by(experiment_id=exp_id_int).delete()
        db.session.delete(exp)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        target = current_experiment_id if current_experiment_id.isdigit() else ''
        return _redirect_to(target, 'Delete failed. Please try again.')

    if current_experiment_id.isdigit() and int(current_experiment_id) == exp_id_int:
        next_exp = Experiment.query.order_by(Experiment.created_at.desc()).first()
        next_id = str(next_exp.experiment_id) if next_exp else ''
        return _redirect_to(next_id, 'Experiment deleted.')

    target = current_experiment_id if current_experiment_id.isdigit() else ''
    return _redirect_to(target, 'Experiment deleted.')

# Route to handle UniProt accession submission  
@staging_bp.post('/uniprot')
def fetch_uniprot():
    from flask_login import current_user
    from datetime import datetime
    
    accession = request.form.get('accession', '').strip()
    if not accession:
        return redirect(url_for('staging.create_experiment', wt_message='Missing accession'))

    # 1) create experiment with default name
    default_name = f"Experiment {accession} {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    exp = Experiment(
        name=default_name,
        user_id=current_user.user_id if current_user.is_authenticated else 1,
        wt_id=0  # Placeholder
    )
    db.session.add(exp)
    db.session.commit()  # exp.experiment_id now exists

    # 2) create WT row (stub for now; later fill with UniProtService)
    wt = WildtypeProtein(
        experiment_id=exp.experiment_id,
        uniprot_accession=accession,
        wt_protein_sequence=None,
        features_json=None,
        protein_length=None,
        plasmid_length=None
    )
    db.session.add(wt)
    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return redirect(url_for(
            'staging.create_experiment',
            experiment_id=str(exp.experiment_id),
            wt_message='WT storage table is missing in the database. Run DB setup/migrations for staging tables.'
        ))

    try:
        result = UniprotService.fetch(accession)
    except UniprotServiceError as e:
        db.session.commit()
        return redirect(url_for(
            "staging.create_experiment",
            experiment_id=str(exp.experiment_id),
            wt_message=str(e)
        ))

    # save WT results and update experiment name with protein name if available
    wt.wt_protein_sequence = result["sequence"]
    wt.protein_length = result["protein_length"]
    wt.features_json = json.dumps(result["features"])

    # Update experiment name with protein name if available
    if result.get("protein_name"):
        exp.name = f"{result['protein_name']} ({accession})"

    try:
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return redirect(url_for(
            'staging.create_experiment',
            experiment_id=str(exp.experiment_id),
            wt_message='Failed to save WT results. Verify staging tables exist and are up to date.'
        ))

    return redirect(url_for(
        'staging.create_experiment',
        experiment_id=str(exp.experiment_id),
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
    
    exp = Experiment.query.filter_by(experiment_id=exp_id_int).first()

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
