import json
import os
from flask import (
    jsonify, render_template, request, redirect,
    url_for, Response, current_app,
    session as flask_session,
)
from flask_login import login_required, current_user
from app.services.staging.parse_fasta import parse_fasta
from app.models import Experiment, WildtypeProtein, ProteinFeature
from app.extensions import db
from app.services.staging.uniprot_service import UniprotService, UniprotServiceError
from app.services.staging.plasmid_validator import validate_plasmid
from app.services.staging.backtranslate import backtranslate

from .. import staging_bp


# ---------- session-based validation helpers ----------

def _get_validation_from_session(experiment_id):
    """Retrieve validation dict stored in Flask session, or None."""
    key = f"validation_{experiment_id}"
    return flask_session.get(key)


def _save_validation_to_session(experiment_id, result):
    """Store a validation result dict in Flask session."""
    key = f"validation_{experiment_id}"
    flask_session[key] = {
        "is_valid": bool(result.is_valid),
        "identity": float(result.identity),
        "coverage": float(result.coverage),
        "strand": str(result.strand),
        "start_nt": int(result.start_nt),
        "end_nt": int(result.end_nt),
        "wraps": bool(result.wraps),
        "message": str(result.message),
    }


class _ValidationProxy:
    """Lightweight object so templates can use validation.is_valid etc."""
    def __init__(self, d):
        for k, v in d.items():
            setattr(self, k, v)


# ---------- session-based parsing result helpers ----------

def _sanitize_for_json(obj):
    """Recursively convert numpy/non-native types to JSON-safe Python types."""
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(i) for i in obj]
    # numpy / C-extension bools
    if hasattr(obj, '__bool__') and type(obj).__name__ in ('bool_', 'numpy.bool_'):
        return bool(obj)
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return obj
    if isinstance(obj, int):
        return obj
    try:
        # Catch-all for numpy scalars
        if hasattr(obj, 'item'):
            return obj.item()
    except Exception:
        pass
    return obj


def _save_parsing_result_to_session(experiment_id, result_dict):
    """Store parsing result dict in Flask session."""
    key = f"parsing_result_{experiment_id}"
    flask_session[key] = _sanitize_for_json(result_dict)


def _get_parsing_result_from_session(experiment_id):
    """Retrieve parsing result dict from Flask session, or None."""
    key = f"parsing_result_{experiment_id}"
    return flask_session.get(key)


# ---------- routes ----------

@staging_bp.get('/')
@login_required
def create_experiment():
    experiment_id = request.args.get('experiment_id', '').strip()
    wt_message = request.args.get('wt_message', '').strip()
    analysis_message = request.args.get('analysis_message', '').strip()
    sequence_message = request.args.get('sequence_message', '').strip()

    wt = None
    validation = None
    parsing_result = None
    analysis_outputs = {}

    # Auto-load the user's latest experiment if none specified
    if not experiment_id and current_user.is_authenticated:
        latest = (Experiment.query
                  .filter_by(user_id=current_user.user_id)
                  .order_by(Experiment.created_at.desc())
                  .first())
        if latest:
            experiment_id = str(latest.experiment_id)

    if experiment_id and experiment_id.isdigit():
        exp = Experiment.query.get(int(experiment_id))
        if exp and exp.wt_id:
            wt = WildtypeProtein.query.get(exp.wt_id)

        # Session-based validation (no DB table needed)
        val_dict = _get_validation_from_session(experiment_id)
        if val_dict:
            validation = _ValidationProxy(val_dict)

        # Session-based parsing results
        parsing_dict = _get_parsing_result_from_session(experiment_id)
        if parsing_dict:
            parsing_result = _ValidationProxy(parsing_dict)

        # Analysis output files — scoped per experiment
        gen_dir = os.path.join(current_app.root_path, "static", "generated", str(experiment_id))
        plot_path = os.path.join(gen_dir, "activity_distribution.png")
        top10_path = os.path.join(gen_dir, "top10_variants.csv")
        qc_path = os.path.join(gen_dir, "stage4_qc_debug.csv")

        sub = f"generated/{experiment_id}"
        analysis_outputs = {
            "plot": {
                "url": url_for("static", filename=f"{sub}/activity_distribution.png"),
                "label": "Activity distribution plot",
                "exists": os.path.exists(plot_path),
            },
            "top10": {
                "url": url_for("static", filename=f"{sub}/top10_variants.csv"),
                "label": "Top 10 variants (CSV)",
                "exists": os.path.exists(top10_path),
            },
            "qc": {
                "url": url_for("static", filename=f"{sub}/stage4_qc_debug.csv"),
                "label": "Stage 4 QC debug (CSV)",
                "exists": os.path.exists(qc_path),
            },
        }

    # Load user's experiments for the sidebar
    experiments = []
    if current_user.is_authenticated:
        experiments = (Experiment.query
                       .filter_by(user_id=current_user.user_id)
                       .order_by(Experiment.created_at.desc())
                       .all())

    return render_template(
        "staging/create_experiment.html",
        experiment_id=experiment_id,
        wt=wt,
        validation=validation,
        parsing_result=parsing_result,
        wt_message=wt_message,
        analysis_message=analysis_message,
        analysis_outputs=analysis_outputs,
        sequence_message=sequence_message,
        experiments=experiments,
    )


# ---------- Delete experiment ----------

@staging_bp.post('/delete/<int:experiment_id>')
@login_required
def delete_experiment(experiment_id):
    from flask import flash
    exp = Experiment.query.get(experiment_id)
    if not exp:
        flash('Experiment not found.', 'danger')
        return redirect(url_for('staging.create_experiment'))
    if exp.user_id != current_user.user_id:
        flash('You can only delete your own experiments.', 'danger')
        return redirect(url_for('staging.create_experiment'))

    try:
        db.session.delete(exp)   # cascade="all, delete-orphan" handles children
        db.session.commit()
        # Clear any session caches
        flask_session.pop(f"validation_{experiment_id}", None)
        flask_session.pop(f"parsing_result_{experiment_id}", None)
        flash(f'Experiment #{experiment_id} deleted.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'Delete failed: {exc}', 'danger')

    return redirect(url_for('staging.create_experiment'))


# ---------- Rename experiment ----------

@staging_bp.post('/experiment/rename')
@login_required
def rename_experiment():
    from flask import flash
    experiment_id = request.form.get('experiment_id', '').strip()
    new_name = request.form.get('name', '').strip()

    if not experiment_id.isdigit():
        return redirect(url_for('staging.create_experiment'))

    if not new_name:
        flash('Experiment name cannot be empty.', 'danger')
        return redirect(url_for('staging.create_experiment', experiment_id=experiment_id))

    exp = Experiment.query.get(int(experiment_id))
    if not exp or exp.user_id != current_user.user_id:
        flash('Experiment not found.', 'danger')
        return redirect(url_for('staging.create_experiment'))

    exp.name = new_name[:255]
    db.session.commit()
    flash(f'Renamed to "{exp.name}".', 'success')
    return redirect(url_for('staging.create_experiment', experiment_id=experiment_id))


# ---------- Create blank experiment ----------

@staging_bp.post('/experiment/new')
@login_required
def create_new_blank_experiment():
    """Create a blank experiment so user can configure it step by step."""
    from flask import flash
    from datetime import datetime

    default_name = f"Experiment {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    exp = Experiment(
        name=default_name,
        user_id=current_user.user_id,
        wt_id=0,  # placeholder — updated when WT is fetched in Step A
    )
    db.session.add(exp)
    try:
        db.session.commit()
        flash(f'Created experiment #{exp.experiment_id}.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'Could not create experiment: {exc}', 'danger')
        return redirect(url_for('staging.create_experiment'))

    return redirect(url_for('staging.create_experiment', experiment_id=str(exp.experiment_id)))


# ---------- Analysis & Sequence routes (from teammate) ----------

@staging_bp.post('/analysis/run')
@login_required
def run_analysis():
    experiment_id = request.form.get('experiment_id', '').strip()
    if not experiment_id.isdigit():
        return redirect(url_for('staging.create_experiment', analysis_message='Missing experiment_id.'))

    exp_id_int = int(experiment_id)
    prev_env = os.getenv("EXPERIMENT_ID")
    os.environ["EXPERIMENT_ID"] = str(exp_id_int)

    try:
        from app.services.analysis import report
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
@login_required
def run_sequence():
    experiment_id = request.form.get('experiment_id', '').strip()
    if not experiment_id.isdigit():
        return redirect(url_for('staging.create_experiment', sequence_message='Missing experiment_id.'))

    try:
        from app.jobs.run_sequence_processing import run_sequence_processing
        run_sequence_processing(int(experiment_id))
        message = "Sequence processing completed. Outputs are stored in the database."
    except Exception as exc:
        message = f"Sequence processing failed: {exc}"

    return redirect(url_for('staging.create_experiment', experiment_id=experiment_id, sequence_message=message))


# ---------- UniProt fetch (your stable version) ----------

@staging_bp.post('/uniprot')
@login_required
def fetch_uniprot():
    accession = request.form.get('accession', '').strip()
    experiment_id = request.form.get('experiment_id', '').strip()
    experiment_name = request.form.get('experiment_name', '').strip()

    if not accession:
        return redirect(url_for('staging.create_experiment', wt_message='Missing accession'))

    try:
        result = UniprotService.fetch(accession)
    except UniprotServiceError as e:
        return redirect(url_for(
            'staging.create_experiment',
            experiment_id=experiment_id or '',
            wt_message=str(e),
        ))

    sequence = result["sequence"]
    protein_length = result["protein_length"]
    features = result.get("features", [])

    # Generate a placeholder plasmid via back-translation
    placeholder_plasmid = backtranslate(sequence)

    # ── Reuse or create a global WT protein ──────────────────────
    # uniprot_id has a UNIQUE constraint (global, not per-user),
    # so look up by accession alone.  Any user can share the same
    # physical protein row.
    wt = WildtypeProtein.query.filter_by(uniprot_id=accession).first()
    if wt:
        # Update the sequence / placeholder plasmid in case UniProt changed
        wt.amino_acid_sequence = sequence
        wt.sequence_length = protein_length
        wt.plasmid_sequence = placeholder_plasmid
        wt.protein_name = result.get("protein_name") or wt.protein_name
        wt.organism = result.get("organism") or wt.organism
    else:
        wt = WildtypeProtein(
            user_id=current_user.user_id,
            uniprot_id=accession,
            protein_name=result.get("protein_name"),
            organism=result.get("organism"),
            amino_acid_sequence=sequence,
            sequence_length=protein_length,
            plasmid_sequence=placeholder_plasmid,
        )
        db.session.add(wt)
        db.session.flush()          # get wt.wt_id

    # ── Attach to existing or new experiment ──────────────────────
    if experiment_id and experiment_id.isdigit():
        exp = Experiment.query.get(int(experiment_id))
        if not exp:
            return redirect(url_for('staging.create_experiment',
                                    wt_message='Experiment not found'))
        exp.wt_id = wt.wt_id
        # Auto-update experiment name with protein info if still default
        protein_name = result.get("protein_name")
        if protein_name and (not exp.name or exp.name.startswith("Experiment ")):
            exp.name = f"{protein_name} ({accession})"
    else:
        protein_name = result.get("protein_name")
        exp = Experiment(
            user_id=current_user.user_id,
            wt_id=wt.wt_id,
            name=experiment_name or (f"{protein_name} ({accession})" if protein_name else f"Experiment ({accession})"),
        )
        db.session.add(exp)
        db.session.flush()
        experiment_id = str(exp.experiment_id)

    # ── Save protein features ────────────────────────────────────
    ProteinFeature.query.filter_by(wt_id=wt.wt_id).delete()
    for feat in features:
        pf = ProteinFeature(
            wt_id=wt.wt_id,
            feature_type=feat.get("type", "unknown"),
            description=feat.get("description", ""),
            start_position=feat.get("start") or 0,
            end_position=feat.get("end") or 0,
        )
        db.session.add(pf)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return redirect(url_for(
            'staging.create_experiment',
            experiment_id=experiment_id or '',
            wt_message=f'Database error: {exc}',
        ))

    return redirect(url_for(
        'staging.create_experiment',
        experiment_id=experiment_id,
        wt_message='Fetched WT sequence + features successfully.',
    ))


# ---------- Plasmid upload (your stable version) ----------

@staging_bp.post('/plasmid')
@login_required
def upload_plasmid():
    experiment_id = request.form.get('experiment_id', '').strip()
    file = request.files.get('plasmid_fasta')

    if not experiment_id.isdigit():
        return redirect(url_for('staging.create_experiment', wt_message='Invalid experiment_id'))

    exp_id_int = int(experiment_id)
    exp = Experiment.query.get(exp_id_int)
    if not exp or not exp.wt_id:
        return redirect(url_for('staging.create_experiment', wt_message='Fetch WT first.'))

    wt = WildtypeProtein.query.get(exp.wt_id)
    if not wt:
        return redirect(url_for('staging.create_experiment', wt_message='WT protein not found. Fetch WT first.'))

    if not file:
        return redirect(url_for('staging.create_experiment', experiment_id=experiment_id, wt_message='No file uploaded'))

    try:
        dna = parse_fasta(file.read())
    except ValueError as e:
        return redirect(url_for('staging.create_experiment', experiment_id=experiment_id, wt_message=str(e)))

    # Store real plasmid (overwrites the back-translated placeholder)
    wt.plasmid_sequence = dna

    if not wt.amino_acid_sequence:
        return redirect(url_for(
            'staging.create_experiment',
            experiment_id=experiment_id,
            wt_message='WT protein sequence missing. Fetch WT again.',
        ))

    result = validate_plasmid(wt.amino_acid_sequence, dna)

    # Store validation result in Flask session (no DB table needed)
    _save_validation_to_session(experiment_id, result)

    db.session.commit()

    return redirect(url_for(
        'staging.create_experiment',
        experiment_id=experiment_id,
        wt_message='Plasmid validated.' if result.is_valid else 'Plasmid invalid (see details).',
    ))


# ---------- Dev helper ----------

@staging_bp.get('/dev/plasmid_fasta/<int:experiment_id>')
@login_required
def dev_plasmid_fasta(experiment_id: int):
    exp = Experiment.query.get(experiment_id)
    if not exp or not exp.wt_id:
        return Response("Experiment or WT not found.", status=404)

    wt = WildtypeProtein.query.get(exp.wt_id)
    if not wt or not wt.amino_acid_sequence:
        return Response("WT protein sequence not found for this experiment.", status=404)

    dna = backtranslate(wt.amino_acid_sequence)

    fasta = f">dev_plasmid_experiment_{experiment_id}\n"
    for i in range(0, len(dna), 70):
        fasta += dna[i:i+70] + "\n"

    resp = Response(fasta, mimetype='application/x-fasta')
    resp.headers['Content-Disposition'] = f'attachment; filename=dev_plasmid_experiment_{experiment_id}.fasta'
    return resp
