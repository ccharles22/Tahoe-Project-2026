"""Ownership and authorization helpers for staging resources."""

from flask_login import current_user
from sqlalchemy import text

from app.extensions import db


LATEST_ACTIVITY_SCORE_SQL = """
SELECT
  m.variant_id,
  m.value AS activity_score
FROM metrics m
JOIN (
  SELECT variant_id, MAX(metric_id) AS metric_id
  FROM metrics
  WHERE metric_name = 'activity_score'
    AND metric_type = 'derived'
  GROUP BY variant_id
) latest ON latest.metric_id = m.metric_id
"""


def get_owned_variant_or_none(variant_id: int):
    """Return variant row if it belongs to current user, else None."""
    row = db.session.execute(
        text(
            f"""
            SELECT
              v.variant_id,
              v.plasmid_variant_index,
              v.assembled_dna_sequence,
              v.protein_sequence,
              v.extra_metadata,
              v.parent_variant_id,
              g.generation_number,
              g.experiment_id,
              e.user_id,
              act.activity_score
            FROM variants v
            JOIN generations g ON g.generation_id = v.generation_id
            JOIN experiments e ON e.experiment_id = g.experiment_id
            LEFT JOIN (
              {LATEST_ACTIVITY_SCORE_SQL}
            ) act ON act.variant_id = v.variant_id
            WHERE v.variant_id = :vid
            LIMIT 1
            """
        ),
        {'vid': variant_id},
    ).mappings().first()

    if not row or int(row['user_id']) != int(current_user.user_id):
        return None
    return row


def experiment_owned_by_current_user(experiment_id: int) -> bool:
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
        {'eid': experiment_id, 'uid': int(current_user.user_id)},
    ).scalar()
    return bool(owned)
