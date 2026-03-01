"""Session-backed state helpers used by staging routes."""

from __future__ import annotations

from flask import session as flask_session
from sqlalchemy import text

from app.extensions import db


class ValidationProxy:
    """Lightweight object so templates can use obj.attr access."""

    def __init__(self, data):
        for key, value in data.items():
            setattr(self, key, value)


def sanitize_for_json(obj):
    """Recursively convert non-native scalar values to JSON-safe types."""
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(i) for i in obj]
    if hasattr(obj, '__bool__') and type(obj).__name__ in ('bool_', 'numpy.bool_'):
        return bool(obj)
    if isinstance(obj, (bool, float, int)):
        return obj
    try:
        if hasattr(obj, 'item'):
            return obj.item()
    except Exception:
        pass
    return obj


def get_validation_from_session(experiment_id):
    """Return saved validation payload for an experiment, if present."""
    key = f'validation_{experiment_id}'
    return flask_session.get(key)


def clear_validation_from_session(experiment_id):
    """Remove only the saved validation payload for one experiment."""
    flask_session.pop(f'validation_{experiment_id}', None)


def save_validation_to_session(experiment_id, result):
    """Persist plasmid validation results in session storage."""
    key = f'validation_{experiment_id}'
    flask_session[key] = {
        'is_valid': bool(result.is_valid),
        'identity': float(result.identity),
        'coverage': float(result.coverage),
        'strand': str(result.strand),
        'start_nt': int(result.start_nt),
        'end_nt': int(result.end_nt),
        'wraps': bool(result.wraps),
        'message': str(result.message),
        'genetic_code_used': int(result.genetic_code_used),
    }


def save_parsing_result_to_session(experiment_id, result_dict):
    """Persist parsing results in session storage using JSON-safe values."""
    key = f'parsing_result_{experiment_id}'
    flask_session[key] = sanitize_for_json(result_dict)


def get_parsing_result_from_session(experiment_id):
    """Return saved parsing payload for an experiment, if present."""
    key = f'parsing_result_{experiment_id}'
    return flask_session.get(key)


def normalize_parsing_result(result_dict):
    """Backfill expected parsing keys for backward-compatible template access."""
    if not isinstance(result_dict, dict):
        return result_dict
    out = dict(result_dict)
    out.setdefault('total_records', 0)
    out.setdefault('inserted_count', 0)
    out.setdefault('updated_count', 0)
    out.setdefault('warnings', [])
    out.setdefault('warnings_count', len(out.get('warnings', []) or []))
    out.setdefault('errors', [])
    out.setdefault('detected_fields', [])
    return out


def recover_parsing_result_from_db(experiment_id: int):
    """Rebuild minimal parsing state from persisted variant rows."""
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
            {'eid': int(experiment_id)},
        ).scalar()
    except Exception:
        db.session.rollback()
        return None

    total = int(total_records or 0)
    if total <= 0:
        return None

    return {
        'success': True,
        'total_records': total,
        'inserted_count': 0,
        'updated_count': 0,
        'warnings': [],
        'warnings_count': 0,
        'detected_fields': [],
        'errors': [],
        'counts_estimated': True,
    }


def save_sequence_status_to_session(experiment_id, status_dict):
    """Persist sequence run status and error details in session storage."""
    key = f'sequence_status_{experiment_id}'
    flask_session[key] = sanitize_for_json(status_dict)


def get_sequence_status_from_session(experiment_id):
    """Return saved sequence status for an experiment, if present."""
    key = f'sequence_status_{experiment_id}'
    return flask_session.get(key)


def clear_sequence_status_from_session(experiment_id):
    """Remove only the saved sequence status for one experiment."""
    flask_session.pop(f'sequence_status_{experiment_id}', None)


def mark_sequence_reprocess_required(experiment_id):
    """Mark sequence outputs as stale after WT/plasmid/upload changes."""
    flask_session[f'sequence_reprocess_required_{experiment_id}'] = True


def is_sequence_reprocess_required(experiment_id) -> bool:
    """Return True when a full sequence rerun is still required."""
    return bool(flask_session.get(f'sequence_reprocess_required_{experiment_id}', False))


def clear_sequence_reprocess_required(experiment_id):
    """Clear the stale-sequence marker after a successful rerun."""
    flask_session.pop(f'sequence_reprocess_required_{experiment_id}', None)


def clear_experiment_session_state(experiment_id: int):
    """Remove all staging session keys tied to one experiment."""
    flask_session.pop(f'validation_{experiment_id}', None)
    flask_session.pop(f'parsing_result_{experiment_id}', None)
    flask_session.pop(f'sequence_status_{experiment_id}', None)
    flask_session.pop(f'sequence_reprocess_required_{experiment_id}', None)
