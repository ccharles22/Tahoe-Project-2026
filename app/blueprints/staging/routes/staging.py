"""Staging workspace page route and view-level orchestration."""

import os
import secrets

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user
from sqlalchemy import text

from app.extensions import bcrypt, db
from app.models import Experiment, User, WildtypeProtein
from app.services.staging.session_state import (
    ValidationProxy,
    get_parsing_result_from_session,
    get_sequence_status_from_session,
    get_validation_from_session,
    normalize_parsing_result,
    recover_parsing_result_from_db,
    save_parsing_result_to_session,
)
from app.services.staging.workspace_data import infer_scoring_metadata, load_kpis, load_top10_rows

from .. import staging_bp


@staging_bp.get('/')
def create_experiment():
    """Render staging UI for the selected experiment (or latest experiment)."""
    if not current_user.is_authenticated:
        try:
            guest_suffix = secrets.token_hex(6)
            guest_username = f"guest_{guest_suffix}"
            guest_email = f"{guest_username}@guest.local"
            guest_password = secrets.token_urlsafe(24)
            guest_user = User(
                username=guest_username,
                email=guest_email,
                password_hash=bcrypt.generate_password_hash(guest_password).decode("utf-8"),
            )
            db.session.add(guest_user)
            db.session.commit()
            login_user(guest_user, remember=False)
            flash("Continuing as guest. Sign in later to keep long-term access to your work.", "info")
        except Exception:
            db.session.rollback()
            flash("Unable to start a guest session right now. Please sign in and try again.", "error")
            return redirect(url_for("auth.login"))

    experiment_id = request.args.get('experiment_id', '').strip()
    wt_message = request.args.get('wt_message', '').strip()
    analysis_message = request.args.get('analysis_message', '').strip()
    sequence_message = request.args.get('sequence_message', '').strip()

    wt = None
    validation = None
    parsing_result = None
    analysis_outputs = {}
    top10_rows = []
    kpis = {
        'total_records': 0,
        'generations_covered': None,
        'activity_mean': None,
        'activity_median': None,
        'activity_best': None,
        'mutated_percent': None,
    }
    sequence_status = None
    selected_experiment_name = None
    methods_panel = {
        'wt_accession': 'N/A',
        'records': 0,
        'generation_range': 'N/A',
        'baseline_used': 'pending',
        'scoring_method': 'pending',
        'mutation_calling': 'pending',
    }

    if not experiment_id and current_user.is_authenticated:
        latest = (
            Experiment.query.filter_by(user_id=current_user.user_id)
            .order_by(Experiment.created_at.desc())
            .first()
        )
        if latest:
            experiment_id = str(latest.experiment_id)

    if experiment_id and experiment_id.isdigit():
        exp = Experiment.query.get(int(experiment_id))
        if exp and exp.name:
            selected_experiment_name = exp.name.strip() or None
        if exp and exp.wt_id:
            wt = WildtypeProtein.query.get(exp.wt_id)
            if wt and wt.uniprot_id:
                methods_panel['wt_accession'] = wt.uniprot_id

        val_dict = get_validation_from_session(experiment_id)
        if val_dict:
            validation = ValidationProxy(val_dict)

        parsing_dict = get_parsing_result_from_session(experiment_id)
        if parsing_dict:
            parsing_dict = normalize_parsing_result(parsing_dict)
            save_parsing_result_to_session(experiment_id, parsing_dict)
            parsing_result = ValidationProxy(parsing_dict)
        else:
            recovered = recover_parsing_result_from_db(int(experiment_id))
            if recovered:
                save_parsing_result_to_session(experiment_id, recovered)
                parsing_result = ValidationProxy(recovered)

        sequence_status = get_sequence_status_from_session(experiment_id)
        sequence_status_code = str(sequence_status.get('status', '')).lower() if sequence_status else ''
        sequence_summary = (sequence_status.get('summary') or '').strip() if sequence_status else ''
        sequence_completed = sequence_status_code == 'success' or (
            'sequence processing completed' in sequence_message.lower()
        )
        sequence_failed = sequence_status_code == 'failed' or (
            'sequence processing failed' in sequence_message.lower()
        )
        sequence_failure_reason = sequence_summary or sequence_message.replace('Sequence processing failed: ', '')
        try:
            # Session state can be stale; persisted sequence analyses still indicate completion.
            sequence_analysis_count = db.session.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM variant_sequence_analysis
                    WHERE experiment_id = :eid
                    """
                ),
                {'eid': int(experiment_id)},
            ).scalar()
            if int(sequence_analysis_count or 0) > 0:
                sequence_completed = True
        except Exception:
            db.session.rollback()

        gen_dir = os.path.join(current_app.root_path, 'static', 'generated', str(experiment_id))
        plot_path = os.path.join(gen_dir, 'activity_distribution.png')
        top10_csv_path = os.path.join(gen_dir, 'top10_variants.csv')
        top10_png_path = os.path.join(gen_dir, 'top10_variants.png')
        lineage_path = os.path.join(gen_dir, 'lineage.png')
        protein_network_path = os.path.join(gen_dir, 'protein_similarity.png')
        qc_path = os.path.join(gen_dir, 'stage4_qc_debug.csv')

        sub = f'generated/{experiment_id}'
        analysis_outputs = {
            'plot': {
                'url': url_for('static', filename=f'{sub}/activity_distribution.png'),
                'label': 'Activity Score Distribution',
                'exists': os.path.exists(plot_path),
            },
            'top10_png': {
                'url': url_for('static', filename=f'{sub}/top10_variants.png'),
                'label': 'Top 10 Variants',
                'exists': os.path.exists(top10_png_path),
            },
            'lineage': {
                'url': url_for('static', filename=f'{sub}/lineage.png'),
                'label': 'Variant Lineage',
                'exists': os.path.exists(lineage_path),
            },
            'protein_network': {
                'url': url_for('static', filename=f'{sub}/protein_similarity.png'),
                'label': 'Protein Similarity Network',
                'exists': os.path.exists(protein_network_path),
            },
            'top10': {
                'url': url_for('static', filename=f'{sub}/top10_variants.csv'),
                'label': 'Top 10 variants (CSV)',
                'exists': os.path.exists(top10_csv_path),
            },
            'qc': {
                'url': url_for('static', filename=f'{sub}/stage4_qc_debug.csv'),
                'label': 'Stage 4 QC debug (CSV)',
                'exists': os.path.exists(qc_path),
            },
            'results': {
                'url': url_for('staging.download_experiment_results_csv', experiment_id=int(experiment_id)),
                'label': 'Results CSV (all processed rows)',
                'exists': True,
            },
            'mutation_report': {
                'url': url_for('staging.download_experiment_mutation_report_csv', experiment_id=int(experiment_id)),
                'label': 'Mutation report CSV',
                'exists': bool(sequence_completed),
                'disabled_reason': (
                    sequence_failure_reason if sequence_failed else 'Run sequence processing first.'
                ),
            },
        }
        top10_rows = load_top10_rows(top10_csv_path, int(experiment_id))
        kpis = load_kpis(int(experiment_id))
        methods_panel['records'] = int(kpis.get('total_records') or 0)
        methods_panel['generation_range'] = (
            str(kpis.get('generations_covered')).replace(' to ', '\u2013')
            if kpis.get('generations_covered')
            else 'N/A'
        )
        methods_panel.update(infer_scoring_metadata(qc_path))
        if sequence_completed:
            methods_panel['mutation_calling'] = 'complete'
        elif sequence_failed:
            methods_panel['mutation_calling'] = 'failed'

    experiments = []
    if current_user.is_authenticated:
        try:
            # Prefer the first available generated artifact as the sidebar preview.
            experiments = (
                Experiment.query.filter_by(user_id=current_user.user_id)
                .order_by(Experiment.created_at.desc())
                .all()
            )
            preview_candidates = [
                ('lineage.png', 'Variant lineage'),
                ('protein_similarity.png', 'Protein similarity network'),
                ('activity_distribution.png', 'Activity score distribution'),
                ('top10_variants.png', 'Top 10 variants'),
            ]
            for exp in experiments:
                exp.preview_url = None
                exp.preview_label = None
                exp_id = str(exp.experiment_id)
                exp_gen_dir = os.path.join(current_app.root_path, 'static', 'generated', exp_id)
                for filename, label in preview_candidates:
                    abs_path = os.path.join(exp_gen_dir, filename)
                    if os.path.exists(abs_path):
                        exp.preview_url = url_for('static', filename=f'generated/{exp_id}/{filename}')
                        exp.preview_label = label
                        break
        except Exception:
            db.session.rollback()
            experiments = []

    return render_template(
        'staging/workflow.html',
        experiment_id=experiment_id,
        wt=wt,
        validation=validation,
        parsing_result=parsing_result,
        wt_message=wt_message,
        analysis_message=analysis_message,
        analysis_outputs=analysis_outputs,
        sequence_message=sequence_message,
        sequence_status=sequence_status,
        top10_rows=top10_rows,
        kpis=kpis,
        experiments=experiments,
        selected_experiment_name=selected_experiment_name,
        methods_panel=methods_panel,
    )

