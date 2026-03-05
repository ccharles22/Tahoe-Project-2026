"""Experiment management endpoints for staging."""

from datetime import datetime

from flask import flash, redirect, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Experiment
from app.services.staging.session_state import clear_experiment_session_state

from .. import staging_bp


@staging_bp.post('/delete/<int:experiment_id>')
@login_required
def delete_experiment(experiment_id):
    """Delete an experiment owned by the current user."""
    exp = Experiment.query.get(experiment_id)
    if not exp:
        flash('Experiment not found.', 'danger')
        return redirect(url_for('staging.create_experiment'))
    if exp.user_id != current_user.user_id:
        flash('You can only delete your own experiments.', 'danger')
        return redirect(url_for('staging.create_experiment'))

    try:
        db.session.delete(exp)
        db.session.commit()
        clear_experiment_session_state(experiment_id)
        flash(f'Experiment #{experiment_id} deleted.', 'success')
    except Exception as exc:
        db.session.rollback()
        flash(f'Delete failed: {exc}', 'danger')

    return redirect(url_for('staging.create_experiment'))


@staging_bp.post('/experiment/rename')
@login_required
def rename_experiment():
    """Rename an existing experiment owned by the current user."""
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


@staging_bp.post('/experiment/new')
@login_required
def create_new_blank_experiment():
    """Create a blank experiment so users can configure it step by step."""
    default_name = f"Experiment {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    # wt_id=0 acts as a placeholder until the user associates a WT protein.
    exp = Experiment(
        name=default_name,
        user_id=current_user.user_id,
        wt_id=0,
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
