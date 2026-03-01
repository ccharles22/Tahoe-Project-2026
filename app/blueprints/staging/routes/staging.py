"""Staging workspace page route and view-level orchestration."""

from collections import Counter
import glob
import os
import secrets

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user
from sqlalchemy import text

from app.extensions import bcrypt, db
from app.models import Experiment, User, WildtypeProtein
from app.services.staging.session_state import (
    ValidationProxy,
    clear_sequence_reprocess_required,
    get_parsing_result_from_session,
    is_sequence_reprocess_required,
    get_sequence_status_from_session,
    get_validation_from_session,
    normalize_parsing_result,
    recover_parsing_result_from_db,
    save_parsing_result_to_session,
)
from app.services.staging.workspace_data import infer_scoring_metadata, load_kpis, load_top10_rows

from .. import staging_bp


def _static_url_with_mtime(filename: str, abs_path: str) -> str:
    """Return a cache-busted static URL for generated assets when present."""
    version = None
    try:
        version = int(os.path.getmtime(abs_path))
    except OSError:
        version = None
    if version is None:
        return url_for('static', filename=filename)
    return url_for('static', filename=filename, v=version)


def _build_wt_insights(wt: WildtypeProtein | None, exp: Experiment | None) -> dict:
    """Build a small WT / UniProt summary for the workspace panels."""
    if not wt:
        return {
            'protein_name': 'N/A',
            'organism': 'N/A',
            'sequence_summary': 'N/A',
            'annotation_summary': 'No UniProt annotations available yet.',
            'feature_highlights': [],
        }

    exp_meta = exp.extra_metadata if exp and isinstance(exp.extra_metadata, dict) else {}
    plasmid_sequence = str(exp_meta.get('wt_plasmid_sequence') or wt.plasmid_sequence or '').strip()
    feature_rows = list(getattr(wt, 'features', []) or [])
    feature_counter = Counter()
    for feature in feature_rows:
        feature_type = str(getattr(feature, 'feature_type', '') or '').strip()
        if feature_type:
            feature_counter[feature_type] += 1

    feature_labels = [
        f"{name} ({count})" if count > 1 else name
        for name, count in feature_counter.most_common(3)
    ]
    if feature_rows:
        if feature_labels:
            annotation_summary = (
                f"{len(feature_rows)} annotations across {', '.join(feature_labels)}."
            )
        else:
            annotation_summary = f"{len(feature_rows)} UniProt annotations stored."
    else:
        annotation_summary = 'No UniProt annotations stored yet.'

    feature_highlights: list[str] = []
    for feature in feature_rows:
        feature_type = str(getattr(feature, 'feature_type', '') or '').strip() or 'Feature'
        description = str(getattr(feature, 'description', '') or '').strip()
        label = description or feature_type
        start = getattr(feature, 'start_position', None)
        end = getattr(feature, 'end_position', None)
        location = ''
        if isinstance(start, int) and start > 0 and isinstance(end, int) and end > 0:
            location = f"{start}" if start == end else f"{start}-{end}"
        elif isinstance(start, int) and start > 0:
            location = f"{start}+"
        highlight = f"{label} ({location})" if location else label
        if highlight not in feature_highlights:
            feature_highlights.append(highlight)
        if len(feature_highlights) >= 3:
            break

    sequence_parts = []
    if wt.sequence_length:
        sequence_parts.append(f"{wt.sequence_length} aa")
    if plasmid_sequence:
        sequence_parts.append(f"{len(plasmid_sequence)} nt plasmid template")

    return {
        'protein_name': wt.protein_name or 'Unnamed reference protein',
        'organism': wt.organism or 'Organism not recorded',
        'sequence_summary': ' / '.join(sequence_parts) if sequence_parts else 'N/A',
        'annotation_summary': annotation_summary,
        'feature_highlights': feature_highlights,
    }


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
            return redirect(url_for("auth.homepage", auth="login"))

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
    wt_insights = _build_wt_insights(None, None)
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
        wt_insights = _build_wt_insights(wt, exp)
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
            sequence_counts = db.session.execute(
                text(
                    """
                    SELECT
                      COUNT(DISTINCT v.variant_id) AS total_variants,
                      COUNT(DISTINCT CASE WHEN vsa.vsa_id IS NOT NULL THEN v.variant_id END) AS analysed_variants
                    FROM public.variants v
                    JOIN public.generations g ON g.generation_id = v.generation_id
                    LEFT JOIN public.variant_sequence_analysis vsa ON vsa.variant_id = v.variant_id
                    WHERE g.experiment_id = :eid
                    """
                ),
                {'eid': int(experiment_id)},
            ).mappings().one()
            if (
                int(sequence_counts['total_variants'] or 0) > 0
                and int(sequence_counts['analysed_variants'] or 0) >= int(sequence_counts['total_variants'] or 0)
            ):
                sequence_completed = True
        except Exception:
            db.session.rollback()
        if (
            sequence_completed
            and is_sequence_reprocess_required(int(experiment_id))
        ):
            clear_sequence_reprocess_required(int(experiment_id))

        gen_dir = os.path.join(current_app.root_path, 'static', 'generated', str(experiment_id))
        plot_path = os.path.join(gen_dir, 'activity_distribution.png')
        top10_csv_path = os.path.join(gen_dir, 'top10_variants.csv')
        top10_png_path = os.path.join(gen_dir, 'top10_variants.png')
        lineage_path = os.path.join(gen_dir, 'lineage.png')
        protein_network_path = os.path.join(gen_dir, 'protein_similarity.png')
        qc_path = os.path.join(gen_dir, 'stage4_qc_debug.csv')
        bonus_dir = os.path.join(gen_dir, 'bonus')
        bonus_surface_path = os.path.join(bonus_dir, 'activity_surface_pca.png')
        bonus_landscape_path = os.path.join(bonus_dir, 'activity_landscape_pca_surface.html')
        bonus_trajectory_path = os.path.join(bonus_dir, 'mutation_trajectory_top10.html')
        bonus_mutation_frequency_path = os.path.join(bonus_dir, 'mutation_frequency_by_position.html')
        bonus_domain_heatmap_path = os.path.join(bonus_dir, 'domain_enrichment_heatmap.html')
        bonus_domain_generation_path = os.path.join(bonus_dir, 'domain_enrichment_latest.html')
        bonus_domain_generation_file = 'domain_enrichment_latest.html'
        if not os.path.exists(bonus_domain_generation_path):
            bonus_domain_generation_matches = glob.glob(os.path.join(bonus_dir, 'domain_enrichment_gen*.html'))
            bonus_domain_generation_matches.sort(key=os.path.getmtime, reverse=True)
            bonus_domain_generation_file = (
                os.path.basename(bonus_domain_generation_matches[0]) if bonus_domain_generation_matches else ''
            )
            bonus_domain_generation_path = bonus_domain_generation_matches[0] if bonus_domain_generation_matches else ''

        bonus_fingerprint_path = os.path.join(bonus_dir, 'mutation_fingerprint_latest.html')
        bonus_fingerprint_file = 'mutation_fingerprint_latest.html'
        if not os.path.exists(bonus_fingerprint_path):
            bonus_fingerprint_matches = glob.glob(os.path.join(bonus_dir, 'mutation_fingerprint_variant*.html'))
            bonus_fingerprint_matches.sort(key=os.path.getmtime, reverse=True)
            bonus_fingerprint_file = os.path.basename(bonus_fingerprint_matches[0]) if bonus_fingerprint_matches else ''
            bonus_fingerprint_path = bonus_fingerprint_matches[0] if bonus_fingerprint_matches else ''

        sub = f'generated/{experiment_id}'
        analysis_outputs = {
            'plot': {
                'url': _static_url_with_mtime(f'{sub}/activity_distribution.png', plot_path),
                'view_url': url_for('distribution', experiment_id=int(experiment_id)),
                'label': 'Activity Score Distribution',
                'exists': os.path.exists(plot_path),
            },
            'top10_png': {
                'url': _static_url_with_mtime(f'{sub}/top10_variants.png', top10_png_path),
                'view_url': url_for('top10', experiment_id=int(experiment_id)),
                'label': 'Top 10 Variants',
                'exists': os.path.exists(top10_png_path),
            },
            'lineage': {
                'url': _static_url_with_mtime(f'{sub}/lineage.png', lineage_path),
                'view_url': url_for('lineage', experiment_id=int(experiment_id)),
                'label': 'Variant Lineage',
                'exists': os.path.exists(lineage_path),
            },
            'protein_network': {
                'url': _static_url_with_mtime(f'{sub}/protein_similarity.png', protein_network_path),
                'view_url': url_for('protein_similarity', experiment_id=int(experiment_id)),
                'label': 'Protein Similarity Network',
                'exists': os.path.exists(protein_network_path),
            },
            'top10': {
                'url': _static_url_with_mtime(f'{sub}/top10_variants.csv', top10_csv_path),
                'label': 'Top 10 variants (CSV)',
                'exists': os.path.exists(top10_csv_path),
            },
            'qc': {
                'url': _static_url_with_mtime(f'{sub}/stage4_qc_debug.csv', qc_path),
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
            'bonus_surface': {
                'url': _static_url_with_mtime(
                    f'{sub}/bonus/activity_surface_pca.png',
                    bonus_surface_path,
                ),
                'label': 'Bonus activity surface (PNG)',
                'exists': os.path.exists(bonus_surface_path),
            },
            'bonus_landscape': {
                'url': _static_url_with_mtime(
                    f'{sub}/bonus/activity_landscape_pca_surface.html',
                    bonus_landscape_path,
                ),
                'label': 'Bonus activity landscape (HTML)',
                'exists': os.path.exists(bonus_landscape_path),
            },
            'bonus_trajectory': {
                'url': _static_url_with_mtime(
                    f'{sub}/bonus/mutation_trajectory_top10.html',
                    bonus_trajectory_path,
                ),
                'label': 'Bonus mutation trajectory (HTML)',
                'exists': os.path.exists(bonus_trajectory_path),
            },
            'bonus_mutation_frequency': {
                'url': _static_url_with_mtime(
                    f'{sub}/bonus/mutation_frequency_by_position.html',
                    bonus_mutation_frequency_path,
                ),
                'label': 'Bonus mutation frequency (HTML)',
                'exists': os.path.exists(bonus_mutation_frequency_path),
            },
            'bonus_domain_heatmap': {
                'url': _static_url_with_mtime(
                    f'{sub}/bonus/domain_enrichment_heatmap.html',
                    bonus_domain_heatmap_path,
                ),
                'label': 'Bonus domain enrichment heatmap (HTML)',
                'exists': os.path.exists(bonus_domain_heatmap_path),
            },
            'bonus_domain_generation': {
                'url': (
                    _static_url_with_mtime(
                        f'{sub}/bonus/{bonus_domain_generation_file}',
                        bonus_domain_generation_path,
                    )
                    if bonus_domain_generation_file
                    else ''
                ),
                'label': 'Bonus domain enrichment (generation) (HTML)',
                'exists': os.path.exists(bonus_domain_generation_path),
            },
            'bonus_fingerprint': {
                'url': (
                    _static_url_with_mtime(
                        f'{sub}/bonus/{bonus_fingerprint_file}',
                        bonus_fingerprint_path,
                    )
                    if bonus_fingerprint_file
                    else ''
                ),
                'label': 'Bonus mutation fingerprint (HTML)',
                'exists': os.path.exists(bonus_fingerprint_path),
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
        wt_insights=wt_insights,
    )
