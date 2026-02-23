import csv
import io
import json
import os
import sys
import logging
import threading
import subprocess
import traceback
from flask import (
    jsonify, render_template, request, redirect,
    url_for, Response, current_app,
    session as flask_session,
)
from flask_login import login_required, current_user
from sqlalchemy import text
from app.services.staging.parse_fasta import parse_fasta
from app.models import Experiment, WildtypeProtein, ProteinFeature
from app.extensions import db
from app.services.sequence.uniprot_service import (
    UniProtRetrievalError,
    acquire_uniprot_entry_with_features,
)
from app.services.staging.plasmid_validator import validate_plasmid
from app.services.staging.backtranslate import backtranslate

from .. import staging_bp

logger = logging.getLogger(__name__)

# ---------- session-based validation helpers ----------
# Notes:
# - Validation/parsing artifacts are intentionally stored in Flask session
#   (scoped by experiment id) instead of persisted models.
# - This keeps staging iteration schema-light while preserving per-experiment UI state.

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


def _normalize_parsing_result(result_dict):
    """Backfill expected parsing fields for older session payloads."""
    if not isinstance(result_dict, dict):
        return result_dict
    out = dict(result_dict)
    out.setdefault("total_records", 0)
    out.setdefault("inserted_count", 0)
    out.setdefault("updated_count", 0)
    out.setdefault("warnings", [])
    out.setdefault("warnings_count", len(out.get("warnings", []) or []))
    out.setdefault("errors", [])
    out.setdefault("detected_fields", [])
    return out


def _recover_parsing_result_from_db(experiment_id: int):
    """
    Rebuild a minimal parsing result from persisted DB rows.

    Parsing UI state is session-backed; this fallback prevents false
    "No data uploaded" messages when session data has expired.
    """
    try:
        total_records = db.session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM variants v
                JOIN generations g ON g.generation_id = v.generation_id
                WHERE g.experiment_id = :eid
                """
            ),
            {"eid": int(experiment_id)},
        ).scalar()
    except Exception:
        db.session.rollback()
        return None

    total = int(total_records or 0)
    if total <= 0:
        return None

    return {
        "success": True,
        "total_records": total,
        # Insert/update split cannot be reconstructed reliably from current state.
        "inserted_count": 0,
        "updated_count": 0,
        "warnings": [],
        "warnings_count": 0,
        "detected_fields": [],
        "errors": [],
        "counts_estimated": True,
    }


def _save_sequence_status_to_session(experiment_id, status_dict):
    """Store sequence run status and technical details in Flask session."""
    key = f"sequence_status_{experiment_id}"
    flask_session[key] = _sanitize_for_json(status_dict)


def _get_sequence_status_from_session(experiment_id):
    """Retrieve sequence run status from Flask session, or None."""
    key = f"sequence_status_{experiment_id}"
    return flask_session.get(key)


def _generate_protein_network_plot(experiment_id: int) -> tuple[bool, str]:
    """Generate protein similarity network PNG for one experiment."""
    try:
        from app.services.analysis.database import get_conn
        from app.services.analysis.queries import fetch_protein_similarity_nodes
        from app.services.analysis.plots.protein_similarity_network import plot_protein_similarity_network
    except Exception as exc:
        return False, f"Protein network setup failed: {exc}"

    out_dir = os.path.join(current_app.root_path, "static", "generated", str(experiment_id))
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "protein_similarity.png")

    try:
        with get_conn() as conn:
            df_protein = fetch_protein_similarity_nodes(conn, experiment_id)
        if df_protein.empty:
            return False, "Protein network skipped: no variants available."
        if df_protein["protein_sequence"].dropna().empty:
            return False, "Protein network skipped: no protein sequences available."

        plot_protein_similarity_network(
            df_protein,
            out_path,
            id_col="variant_id",
            seq_col="protein_sequence",
            activity_col="activity_score",
            top_col="is_top10",
        )
        return True, "Protein network generated."
    except Exception as exc:
        return False, f"Protein network failed: {exc}"


def _load_top10_rows(csv_path, experiment_id):
    """Load top-10 rows from generated CSV for table rendering."""
    rows = []
    if not os.path.exists(csv_path):
        return rows

    try:
        with open(csv_path, "r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for idx, row in enumerate(reader, start=1):
                if idx > 10:
                    break
                rows.append(
                    {
                        "rank": idx,
                        "generation_number": row.get("generation_number") or row.get("Gen") or "",
                        "variant_index": row.get("plasmid_variant_index") or row.get("Variant") or "",
                        "activity_score": row.get("activity_score") or row.get("Activity score") or "",
                        "protein_mutations": row.get("protein_mutations") or row.get("Protein muts") or "",
                        "variant_id": None,
                    }
                )
    except Exception:
        return []

    keys = []
    for r in rows:
        try:
            gen_num = int(str(r["generation_number"]).strip())
            var_idx = str(r["variant_index"]).strip()
            keys.append((gen_num, var_idx))
        except Exception:
            continue

    if not keys:
        return rows

    clauses = []
    params = {"eid": experiment_id}
    for i, (gen_num, var_idx) in enumerate(keys):
        clauses.append(f"(g.generation_number = :g{i} AND v.plasmid_variant_index = :v{i})")
        params[f"g{i}"] = gen_num
        params[f"v{i}"] = var_idx

    try:
        sql = f"""
            SELECT
              g.generation_number,
              v.plasmid_variant_index,
              MAX(v.variant_id) AS variant_id
            FROM variants v
            JOIN generations g ON g.generation_id = v.generation_id
            WHERE g.experiment_id = :eid
              AND ({' OR '.join(clauses)})
            GROUP BY g.generation_number, v.plasmid_variant_index
        """
        found = db.session.execute(text(sql), params).mappings().all()
        id_map = {
            (int(row["generation_number"]), str(row["plasmid_variant_index"])): int(row["variant_id"])
            for row in found
        }
        for r in rows:
            try:
                key = (int(str(r["generation_number"]).strip()), str(r["variant_index"]).strip())
                r["variant_id"] = id_map.get(key)
            except Exception:
                r["variant_id"] = None
    except Exception:
        db.session.rollback()
        for r in rows:
            r["variant_id"] = None

    return rows


def _run_analysis_background(experiment_id: int, app_obj) -> None:
    """Run analysis in a background thread to avoid blocking web requests."""
    repo_root = os.path.dirname(app_obj.root_path)
    env = os.environ.copy()
    env["EXPERIMENT_ID"] = str(experiment_id)
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "app.services.analysis.report"],
            cwd=repo_root,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            logger.error(
                "Background analysis failed for experiment %s (code=%s): %s",
                experiment_id,
                proc.returncode,
                proc.stderr[-2000:] if proc.stderr else "no stderr",
            )
            return

        with app_obj.app_context():
            generated, protein_msg = _generate_protein_network_plot(experiment_id)
            logger.info(
                "Background analysis complete for experiment %s: %s",
                experiment_id,
                "Protein network generated." if generated else protein_msg,
            )
    except Exception:
        logger.exception("Background analysis crashed for experiment %s", experiment_id)


def _run_sequence_background(experiment_id: int, app_obj) -> None:
    """Run sequence processing in a background thread."""
    with app_obj.app_context():
        try:
            from app.jobs.run_sequence_processing import run_sequence_processing
            run_sequence_processing(experiment_id)
            summary = "Sequence processing completed. Outputs are stored in the database."
            logger.info("Background sequence complete for experiment %s: %s", experiment_id, summary)
        except Exception:
            logger.exception("Background sequence failed for experiment %s", experiment_id)


def _load_kpis(experiment_id):
    """Load high-level KPI metrics for staging workspace."""
    kpi = {
        "total_records": 0,
        "generations_covered": None,
        "activity_mean": None,
        "activity_median": None,
        "activity_best": None,
        "mutated_percent": None,
    }

    try:
        total_records = db.session.execute(
            text(
                """
                SELECT COUNT(*)
                FROM variants v
                JOIN generations g ON g.generation_id = v.generation_id
                WHERE g.experiment_id = :eid
                """
            ),
            {"eid": experiment_id},
        ).scalar()
        kpi["total_records"] = int(total_records or 0)

        gen_row = db.session.execute(
            text(
                """
                SELECT MIN(generation_number) AS min_gen, MAX(generation_number) AS max_gen
                FROM generations
                WHERE experiment_id = :eid
                """
            ),
            {"eid": experiment_id},
        ).fetchone()
        if gen_row and gen_row[0] is not None and gen_row[1] is not None:
            kpi["generations_covered"] = f"G{int(gen_row[0])} to G{int(gen_row[1])}"

        activity_row = db.session.execute(
            text(
                """
                SELECT AVG(m.value) AS mean_score, MAX(m.value) AS best_score
                FROM metrics m
                JOIN generations g ON g.generation_id = m.generation_id
                WHERE g.experiment_id = :eid
                  AND m.metric_name = 'activity_score'
                  AND m.metric_type = 'derived'
                """
            ),
            {"eid": experiment_id},
        ).fetchone()
        if activity_row:
            if activity_row[0] is not None:
                kpi["activity_mean"] = float(activity_row[0])
            if activity_row[1] is not None:
                kpi["activity_best"] = float(activity_row[1])

        activity_median = db.session.execute(
            text(
                """
                SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY m.value)
                FROM metrics m
                JOIN generations g ON g.generation_id = m.generation_id
                WHERE g.experiment_id = :eid
                  AND m.metric_name = 'activity_score'
                  AND m.metric_type = 'derived'
                """
            ),
            {"eid": experiment_id},
        ).scalar()
        if activity_median is not None:
            kpi["activity_median"] = float(activity_median)

        analysed_count = db.session.execute(
            text(
                """
                SELECT COUNT(DISTINCT variant_id)
                FROM variant_sequence_analysis
                WHERE experiment_id = :eid
                """
            ),
            {"eid": experiment_id},
        ).scalar()
        mut_count = db.session.execute(
            text(
                """
                SELECT COUNT(DISTINCT vsa.variant_id)
                FROM variant_sequence_analysis vsa
                JOIN variant_mutations vm ON vm.analysis_id = vsa.analysis_id
                WHERE vsa.experiment_id = :eid
                """
            ),
            {"eid": experiment_id},
        ).scalar()
        analysed = int(analysed_count or 0)
        mutated = int(mut_count or 0)
        if analysed > 0:
            kpi["mutated_percent"] = round((mutated / analysed) * 100.0, 1)
    except Exception:
        # Clear aborted transaction state so later queries in this request can run.
        db.session.rollback()
        return kpi

    return kpi


# ---------- routes ----------

@staging_bp.get('/')
@login_required
def create_experiment():
    """Render staging UI for the selected experiment (or latest experiment)."""
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
        "total_records": 0,
        "generations_covered": None,
        "activity_mean": None,
        "activity_median": None,
        "activity_best": None,
        "mutated_percent": None,
    }
    sequence_status = None
    selected_experiment_name = None

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
        if exp and exp.name:
            selected_experiment_name = exp.name.strip() or None
        if exp and exp.wt_id:
            wt = WildtypeProtein.query.get(exp.wt_id)

        # Session-based validation (no DB table needed)
        val_dict = _get_validation_from_session(experiment_id)
        if val_dict:
            validation = _ValidationProxy(val_dict)

        # Session-based parsing results
        parsing_dict = _get_parsing_result_from_session(experiment_id)
        if parsing_dict:
            parsing_dict = _normalize_parsing_result(parsing_dict)
            # Persist normalized shape to prevent repeated legacy-key failures.
            _save_parsing_result_to_session(experiment_id, parsing_dict)
            parsing_result = _ValidationProxy(parsing_dict)
        else:
            recovered = _recover_parsing_result_from_db(int(experiment_id))
            if recovered:
                _save_parsing_result_to_session(experiment_id, recovered)
                parsing_result = _ValidationProxy(recovered)
        sequence_status = _get_sequence_status_from_session(experiment_id)
        sequence_status_code = str(sequence_status.get("status", "")).lower() if sequence_status else ""
        sequence_summary = (sequence_status.get("summary") or "").strip() if sequence_status else ""
        sequence_completed = (
            sequence_status_code == "success"
            or ("sequence processing completed" in sequence_message.lower())
        )
        sequence_failed = (
            sequence_status_code == "failed"
            or ("sequence processing failed" in sequence_message.lower())
        )
        sequence_failure_reason = sequence_summary or sequence_message.replace("Sequence processing failed: ", "")
        try:
            sequence_analysis_count = db.session.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM variant_sequence_analysis
                    WHERE experiment_id = :eid
                    """
                ),
                {"eid": int(experiment_id)},
            ).scalar()
            if int(sequence_analysis_count or 0) > 0:
                sequence_completed = True
        except Exception:
            db.session.rollback()

        # Analysis output files — scoped per experiment
        gen_dir = os.path.join(current_app.root_path, "static", "generated", str(experiment_id))
        plot_path = os.path.join(gen_dir, "activity_distribution.png")
        top10_csv_path = os.path.join(gen_dir, "top10_variants.csv")
        top10_png_path = os.path.join(gen_dir, "top10_variants.png")
        lineage_path = os.path.join(gen_dir, "lineage.png")
        protein_network_path = os.path.join(gen_dir, "protein_similarity.png")
        qc_path = os.path.join(gen_dir, "stage4_qc_debug.csv")

        sub = f"generated/{experiment_id}"
        analysis_outputs = {
            "plot": {
                "url": url_for("static", filename=f"{sub}/activity_distribution.png"),
                "label": "Activity Score Distribution",
                "exists": os.path.exists(plot_path),
            },
            "top10_png": {
                "url": url_for("static", filename=f"{sub}/top10_variants.png"),
                "label": "Top 10 Variants",
                "exists": os.path.exists(top10_png_path),
            },
            "lineage": {
                "url": url_for("static", filename=f"{sub}/lineage.png"),
                "label": "Variant Lineage",
                "exists": os.path.exists(lineage_path),
            },
            "protein_network": {
                "url": url_for("static", filename=f"{sub}/protein_similarity.png"),
                "label": "Protein Similarity Network",
                "exists": os.path.exists(protein_network_path),
            },
            "top10": {
                "url": url_for("static", filename=f"{sub}/top10_variants.csv"),
                "label": "Top 10 variants (CSV)",
                "exists": os.path.exists(top10_csv_path),
            },
            "qc": {
                "url": url_for("static", filename=f"{sub}/stage4_qc_debug.csv"),
                "label": "Stage 4 QC debug (CSV)",
                "exists": os.path.exists(qc_path),
            },
            "results": {
                "url": url_for("staging.download_experiment_results_csv", experiment_id=int(experiment_id)),
                "label": "Results CSV (all processed rows)",
                "exists": True,
            },
            "mutation_report": {
                "url": url_for("staging.download_experiment_mutation_report_csv", experiment_id=int(experiment_id)),
                "label": "Mutation report CSV",
                "exists": bool(sequence_completed),
                "disabled_reason": (
                    sequence_failure_reason if sequence_failed else "Run sequence processing first."
                ),
            },
        }
        top10_rows = _load_top10_rows(top10_csv_path, int(experiment_id))
        kpis = _load_kpis(int(experiment_id))

    # Load user's experiments for the sidebar
    experiments = []
    if current_user.is_authenticated:
        try:
            experiments = (Experiment.query
                           .filter_by(user_id=current_user.user_id)
                           .order_by(Experiment.created_at.desc())
                           .all())
            preview_candidates = [
                ("lineage.png", "Variant lineage"),
                ("protein_similarity.png", "Protein similarity network"),
                ("activity_distribution.png", "Activity score distribution"),
                ("top10_variants.png", "Top 10 variants"),
            ]
            for exp in experiments:
                exp.preview_url = None
                exp.preview_label = None
                exp_id = str(exp.experiment_id)
                exp_gen_dir = os.path.join(current_app.root_path, "static", "generated", exp_id)
                for filename, label in preview_candidates:
                    abs_path = os.path.join(exp_gen_dir, filename)
                    if os.path.exists(abs_path):
                        exp.preview_url = url_for("static", filename=f"generated/{exp_id}/{filename}")
                        exp.preview_label = label
                        break
        except Exception:
            db.session.rollback()
            experiments = []

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
        sequence_status=sequence_status,
        top10_rows=top10_rows,
        kpis=kpis,
        experiments=experiments,
        selected_experiment_name=selected_experiment_name,
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
        flask_session.pop(f"sequence_status_{experiment_id}", None)
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
    app_obj = current_app._get_current_object()
    t = threading.Thread(
        target=_run_analysis_background,
        args=(exp_id_int, app_obj),
        daemon=True,
        name=f"analysis-exp-{exp_id_int}",
    )
    t.start()
    analysis_message = "Analysis started in background. Refresh in a moment to see outputs."

    return redirect(
        url_for(
            'staging.create_experiment',
            experiment_id=experiment_id,
            analysis_message=analysis_message,
        )
    )


@staging_bp.post('/sequence/run')
@login_required
def run_sequence():
    """Run sequence processing for the experiment and return status via redirect."""
    experiment_id = request.form.get('experiment_id', '').strip()
    if not experiment_id.isdigit():
        return redirect(url_for('staging.create_experiment', sequence_message='Missing experiment_id.'))

    exp_id_int = int(experiment_id)
    try:
        from app.jobs.run_sequence_processing import run_sequence_processing
        run_sequence_processing(exp_id_int)
        message = "Sequence processing completed. Outputs are stored in the database."
        _save_sequence_status_to_session(exp_id_int, {
            "status": "success",
            "summary": message,
            "technical_details": "",
        })
    except Exception as exc:
        message = f"Sequence processing failed: {exc}"
        _save_sequence_status_to_session(exp_id_int, {
            "status": "failed",
            "summary": str(exc),
            "technical_details": traceback.format_exc(),
        })

    return redirect(url_for('staging.create_experiment', experiment_id=experiment_id, sequence_message=message))


# ---------- UniProt fetch (your stable version) ----------

@staging_bp.post('/uniprot')
@login_required
def fetch_uniprot():
    """Fetch UniProt WT, attach/create experiment, then refresh WT feature rows."""
    accession = request.form.get('accession', '').strip()
    experiment_id = request.form.get('experiment_id', '').strip()
    experiment_name = request.form.get('experiment_name', '').strip()

    if not accession:
        return redirect(url_for('staging.create_experiment', wt_message='Missing accession'))

    try:
        entry = acquire_uniprot_entry_with_features(accession)
    except UniProtRetrievalError as e:
        return redirect(url_for(
            'staging.create_experiment',
            experiment_id=experiment_id or '',
            wt_message=str(e),
        ))

    sequence = entry.sequence
    protein_length = entry.length
    features = entry.features

    # Generate a placeholder plasmid via back-translation
    placeholder_plasmid = backtranslate(sequence)

    # ── Reuse or create a global WT protein ──────────────────────
    # uniprot_id has a UNIQUE constraint (global, not per-user),
    # so look up by accession alone.  Any user can share the same
    # physical protein row.
    # Note: updates below will affect all experiments that reference this WT row.
    wt = WildtypeProtein.query.filter_by(uniprot_id=accession).first()
    if wt:
        # Update the sequence / placeholder plasmid in case UniProt changed
        wt.amino_acid_sequence = sequence
        wt.sequence_length = protein_length
        wt.plasmid_sequence = placeholder_plasmid
        wt.protein_name = entry.protein_name or wt.protein_name
        wt.organism = entry.organism or wt.organism
    else:
        wt = WildtypeProtein(
            user_id=current_user.user_id,
            uniprot_id=accession,
            protein_name=entry.protein_name,
            organism=entry.organism,
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
        protein_name = entry.protein_name
        if protein_name and (not exp.name or exp.name.startswith("Experiment ")):
            exp.name = f"{protein_name} ({accession})"
    else:
        protein_name = entry.protein_name
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
            feature_type=feat.feature_type or "unknown",
            description=feat.description or "",
            start_position=feat.begin or 0,
            end_position=feat.end or 0,
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


def _get_owned_variant_or_none(variant_id: int):
    """Return variant row if it belongs to current user, else None."""
    row = db.session.execute(
        text(
            """
            SELECT
              v.variant_id,
              v.plasmid_variant_index,
              v.assembled_dna_sequence,
              v.protein_sequence,
              v.parent_variant_id,
              g.generation_number,
              g.experiment_id,
              e.user_id,
              m.value AS activity_score
            FROM variants v
            JOIN generations g ON g.generation_id = v.generation_id
            JOIN experiments e ON e.experiment_id = g.experiment_id
            LEFT JOIN metrics m
              ON m.variant_id = v.variant_id
             AND m.metric_name = 'activity_score'
             AND m.metric_type = 'derived'
            WHERE v.variant_id = :vid
            LIMIT 1
            """
        ),
        {"vid": variant_id},
    ).mappings().first()

    if not row or int(row["user_id"]) != int(current_user.user_id):
        return None
    return row


def _experiment_owned_by_current_user(experiment_id: int) -> bool:
    """Return True if the experiment belongs to the current user."""
    owned = db.session.execute(
        text(
            """
            SELECT 1
            FROM experiments
            WHERE experiment_id = :eid
              AND user_id = :uid
            LIMIT 1
            """
        ),
        {"eid": experiment_id, "uid": int(current_user.user_id)},
    ).scalar()
    return bool(owned)


@staging_bp.get('/variant/<int:variant_id>/details')
@login_required
def variant_details(variant_id: int):
    row = _get_owned_variant_or_none(variant_id)
    if not row:
        return jsonify({"error": "Variant not found"}), 404

    latest_analysis = db.session.execute(
        text(
            """
            SELECT analysis_id, analysis_json
            FROM variant_sequence_analysis
            WHERE variant_id = :vid
              AND user_id = :uid
            ORDER BY analysed_at DESC, analysis_id DESC
            LIMIT 1
            """
        ),
        {"vid": variant_id, "uid": int(current_user.user_id)},
    ).mappings().first()

    mutations = []
    snippet = ""
    if latest_analysis:
        mut_rows = db.session.execute(
            text(
                """
                SELECT
                  mutation_type,
                  codon_index_1based,
                  aa_position_1based,
                  wt_codon,
                  var_codon,
                  wt_aa,
                  var_aa,
                  notes
                FROM variant_mutations
                WHERE analysis_id = :aid
                ORDER BY aa_position_1based NULLS LAST, codon_index_1based NULLS LAST
                """
            ),
            {"aid": int(latest_analysis["analysis_id"])},
        ).mappings().all()

        for m in mut_rows:
            mutations.append({
                "mutation_type": m["mutation_type"] or "",
                "aa_position": m["aa_position_1based"],
                "codon_index": m["codon_index_1based"],
                "wt_aa": m["wt_aa"] or "",
                "var_aa": m["var_aa"] or "",
                "wt_codon": m["wt_codon"] or "",
                "var_codon": m["var_codon"] or "",
                "notes": m["notes"] or "",
            })

    protein_seq = (row["protein_sequence"] or "").strip()
    if protein_seq and mutations:
        first_pos = mutations[0].get("aa_position")
        if isinstance(first_pos, int) and first_pos > 0:
            idx0 = first_pos - 1
            left = max(0, idx0 - 10)
            right = min(len(protein_seq), idx0 + 11)
            snippet = protein_seq[left:right]

    return jsonify({
        "variant_id": int(row["variant_id"]),
        "variant_index": row["plasmid_variant_index"] or "",
        "generation_number": int(row["generation_number"]) if row["generation_number"] is not None else None,
        "parent_variant_id": row["parent_variant_id"],
        "activity_score": float(row["activity_score"]) if row["activity_score"] is not None else None,
        "protein_snippet": snippet,
        "mutations": mutations,
        "download_urls": {
            "dna_fasta": url_for("staging.download_variant_dna_fasta", variant_id=int(row["variant_id"])),
            "protein_fasta": url_for("staging.download_variant_protein_fasta", variant_id=int(row["variant_id"])),
            "mutation_csv": url_for("staging.download_variant_mutation_csv", variant_id=int(row["variant_id"])),
        },
    })


@staging_bp.get('/variant/<int:variant_id>/download/dna_fasta')
@login_required
def download_variant_dna_fasta(variant_id: int):
    row = _get_owned_variant_or_none(variant_id)
    if not row:
        return Response("Variant not found.", status=404)

    dna = (row["assembled_dna_sequence"] or "").strip()
    if not dna:
        return Response("DNA sequence not available.", status=404)

    fasta = f">variant_{variant_id}_dna\n"
    for i in range(0, len(dna), 70):
        fasta += dna[i:i + 70] + "\n"

    resp = Response(fasta, mimetype='application/x-fasta')
    resp.headers['Content-Disposition'] = f'attachment; filename=variant_{variant_id}_dna.fasta'
    return resp


@staging_bp.get('/variant/<int:variant_id>/download/protein_fasta')
@login_required
def download_variant_protein_fasta(variant_id: int):
    row = _get_owned_variant_or_none(variant_id)
    if not row:
        return Response("Variant not found.", status=404)

    protein = (row["protein_sequence"] or "").strip()
    if not protein:
        return Response("Protein sequence not available. Run sequence processing first.", status=404)

    fasta = f">variant_{variant_id}_protein\n"
    for i in range(0, len(protein), 70):
        fasta += protein[i:i + 70] + "\n"

    resp = Response(fasta, mimetype='application/x-fasta')
    resp.headers['Content-Disposition'] = f'attachment; filename=variant_{variant_id}_protein.fasta'
    return resp


@staging_bp.get('/variant/<int:variant_id>/download/mutation_csv')
@login_required
def download_variant_mutation_csv(variant_id: int):
    row = _get_owned_variant_or_none(variant_id)
    if not row:
        return Response("Variant not found.", status=404)

    latest_analysis = db.session.execute(
        text(
            """
            SELECT analysis_id
            FROM variant_sequence_analysis
            WHERE variant_id = :vid
              AND user_id = :uid
            ORDER BY analysed_at DESC, analysis_id DESC
            LIMIT 1
            """
        ),
        {"vid": variant_id, "uid": int(current_user.user_id)},
    ).scalar()
    if not latest_analysis:
        return Response("No mutation analysis available. Run sequence processing first.", status=404)

    mut_rows = db.session.execute(
        text(
            """
            SELECT
              mutation_type,
              codon_index_1based,
              aa_position_1based,
              wt_codon,
              var_codon,
              wt_aa,
              var_aa,
              notes
            FROM variant_mutations
            WHERE analysis_id = :aid
            ORDER BY aa_position_1based NULLS LAST, codon_index_1based NULLS LAST
            """
        ),
        {"aid": int(latest_analysis)},
    ).mappings().all()

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "mutation_type",
        "codon_index_1based",
        "aa_position_1based",
        "wt_codon",
        "var_codon",
        "wt_aa",
        "var_aa",
        "notes",
    ])
    for m in mut_rows:
        writer.writerow([
            m["mutation_type"],
            m["codon_index_1based"],
            m["aa_position_1based"],
            m["wt_codon"],
            m["var_codon"],
            m["wt_aa"],
            m["var_aa"],
            m["notes"],
        ])

    resp = Response(out.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = f"attachment; filename=variant_{variant_id}_mutations.csv"
    return resp


@staging_bp.get('/experiment/<int:experiment_id>/download/results_csv')
@login_required
def download_experiment_results_csv(experiment_id: int):
    if not _experiment_owned_by_current_user(experiment_id):
        return Response("Experiment not found.", status=404)

    rows = db.session.execute(
        text(
            """
            SELECT
              g.generation_number,
              v.variant_id,
              v.parent_variant_id,
              v.plasmid_variant_index,
              v.assembled_dna_sequence,
              v.protein_sequence,
              MAX(CASE WHEN m.metric_name = 'dna_yield' THEN m.value END) AS dna_yield,
              MAX(CASE WHEN m.metric_name = 'protein_yield' THEN m.value END) AS protein_yield,
              MAX(CASE WHEN m.metric_name = 'activity_score' THEN m.value END) AS activity_score
            FROM generations g
            JOIN variants v ON v.generation_id = g.generation_id
            LEFT JOIN metrics m ON m.variant_id = v.variant_id
            WHERE g.experiment_id = :eid
            GROUP BY
              g.generation_number,
              v.variant_id,
              v.parent_variant_id,
              v.plasmid_variant_index,
              v.assembled_dna_sequence,
              v.protein_sequence
            ORDER BY g.generation_number ASC, v.variant_id ASC
            """
        ),
        {"eid": experiment_id},
    ).mappings().all()

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "experiment_id",
        "generation_number",
        "variant_id",
        "parent_variant_id",
        "plasmid_variant_index",
        "assembled_dna_sequence",
        "protein_sequence",
        "dna_yield",
        "protein_yield",
        "activity_score",
    ])
    for r in rows:
        writer.writerow([
            experiment_id,
            r["generation_number"],
            r["variant_id"],
            r["parent_variant_id"],
            r["plasmid_variant_index"],
            r["assembled_dna_sequence"],
            r["protein_sequence"],
            r["dna_yield"],
            r["protein_yield"],
            r["activity_score"],
        ])

    resp = Response(out.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = f"attachment; filename=experiment_{experiment_id}_results.csv"
    return resp


@staging_bp.get('/experiment/<int:experiment_id>/download/mutation_report_csv')
@login_required
def download_experiment_mutation_report_csv(experiment_id: int):
    if not _experiment_owned_by_current_user(experiment_id):
        return Response("Experiment not found.", status=404)

    rows = db.session.execute(
        text(
            """
            SELECT
              g.generation_number,
              v.variant_id,
              v.plasmid_variant_index,
              v.parent_variant_id,
              vsa.analysis_id,
              vsa.analysed_at,
              vm.mutation_type,
              vm.codon_index_1based,
              vm.aa_position_1based,
              vm.wt_codon,
              vm.var_codon,
              vm.wt_aa,
              vm.var_aa,
              vm.notes
            FROM variant_sequence_analysis vsa
            JOIN variants v ON v.variant_id = vsa.variant_id
            JOIN generations g ON g.generation_id = v.generation_id
            LEFT JOIN variant_mutations vm ON vm.analysis_id = vsa.analysis_id
            WHERE vsa.experiment_id = :eid
              AND vsa.user_id = :uid
            ORDER BY g.generation_number ASC, v.variant_id ASC, vm.aa_position_1based ASC NULLS LAST, vm.codon_index_1based ASC NULLS LAST
            """
        ),
        {"eid": experiment_id, "uid": int(current_user.user_id)},
    ).mappings().all()

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "experiment_id",
        "generation_number",
        "variant_id",
        "plasmid_variant_index",
        "parent_variant_id",
        "analysis_id",
        "analysed_at",
        "mutation_type",
        "codon_index_1based",
        "aa_position_1based",
        "wt_codon",
        "var_codon",
        "wt_aa",
        "var_aa",
        "notes",
    ])
    for r in rows:
        writer.writerow([
            experiment_id,
            r["generation_number"],
            r["variant_id"],
            r["plasmid_variant_index"],
            r["parent_variant_id"],
            r["analysis_id"],
            r["analysed_at"],
            r["mutation_type"],
            r["codon_index_1based"],
            r["aa_position_1based"],
            r["wt_codon"],
            r["var_codon"],
            r["wt_aa"],
            r["var_aa"],
            r["notes"],
        ])

    resp = Response(out.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = f"attachment; filename=experiment_{experiment_id}_mutation_report.csv"
    return resp


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
