"""Workspace data loaders for staging UI panels and summaries."""

from __future__ import annotations

import csv
import os

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

LATEST_MUTATION_TOTAL_SQL = """
SELECT
  m.variant_id,
  m.value AS total_mutations
FROM metrics m
JOIN (
  SELECT variant_id, MAX(metric_id) AS metric_id
  FROM metrics
  WHERE metric_name = 'mutation_total_count'
    AND metric_type = 'derived'
  GROUP BY variant_id
) latest ON latest.metric_id = m.metric_id
"""

LATEST_SYNONYMOUS_COUNTS_SQL = """
SELECT
  m.variant_id,
  m.value AS syn_count
FROM metrics m
JOIN (
  SELECT variant_id, MAX(metric_id) AS metric_id
  FROM metrics
  WHERE metric_name = 'mutation_synonymous_count'
    AND metric_type = 'derived'
  GROUP BY variant_id
) latest ON latest.metric_id = m.metric_id
"""

LATEST_NONSYNONYMOUS_COUNTS_SQL = """
SELECT
  m.variant_id,
  m.value AS non_syn_count
FROM metrics m
JOIN (
  SELECT variant_id, MAX(metric_id) AS metric_id
  FROM metrics
  WHERE metric_name = 'mutation_nonsynonymous_count'
    AND metric_type = 'derived'
  GROUP BY variant_id
) latest ON latest.metric_id = m.metric_id
"""

LATEST_SUCCESS_VSA_SQL = """
SELECT DISTINCT ON (vsa.variant_id)
  vsa.variant_id,
  vsa.status,
  vsa.qc_flags
FROM variant_sequence_analysis vsa
JOIN variants v ON v.variant_id = vsa.variant_id
JOIN generations g ON g.generation_id = v.generation_id
WHERE g.experiment_id = :eid
ORDER BY
  vsa.variant_id,
  COALESCE(vsa.updated_at, vsa.created_at) DESC,
  vsa.vsa_id DESC
"""


def load_top10_rows(csv_path, experiment_id):
    """Load top-10 rows from generated CSV and attach variant ids when possible."""
    rows = []

    # Prefer live DB data so the staging table reflects the latest mutation
    # counts immediately after sequence processing, even if the CSV is stale.
    try:
        db_rows = db.session.execute(
            text(
                f"""
                SELECT
                  v.variant_id,
                  g.generation_number,
                  v.plasmid_variant_index,
                  act.activity_score,
                  COALESCE(
                    CASE
                      WHEN jsonb_typeof(v.extra_metadata->'sequence_analysis'->'mutations') = 'array'
                      THEN jsonb_array_length(v.extra_metadata->'sequence_analysis'->'mutations')
                      ELSE NULL
                    END,
                    CAST(NULLIF(v.extra_metadata->'sequence_analysis'->'mutation_counts'->>'total', '') AS integer),
                    mt.total_mutations
                  ) AS total_mutations
                FROM variants v
                JOIN generations g ON g.generation_id = v.generation_id
                JOIN (
                  {LATEST_ACTIVITY_SCORE_SQL}
                ) act ON act.variant_id = v.variant_id
                LEFT JOIN (
                  {LATEST_MUTATION_TOTAL_SQL}
                ) mt ON mt.variant_id = v.variant_id
                WHERE g.experiment_id = :eid
                ORDER BY act.activity_score DESC
                LIMIT 10
                """
            ),
            {'eid': experiment_id},
        ).mappings().all()

        for idx, row in enumerate(db_rows, start=1):
            activity_value = None
            if row['activity_score'] is not None:
                activity_value = float(row['activity_score'])

            mutation_count = None
            if row['total_mutations'] is not None:
                mutation_count = int(row['total_mutations'])
            rows.append(
                {
                    'rank': idx,
                    'generation_number': int(row['generation_number']),
                    'variant_index': str(row['plasmid_variant_index']),
                    'activity_score': (
                        f'{activity_value:.3f}' if activity_value is not None else ''
                    ),
                    'activity_score_value': activity_value,
                    'protein_mutations': mutation_count,
                    'variant_id': int(row['variant_id']),
                    'is_mutant': mutation_count is not None and mutation_count > 0,
                    'qc_flagged': False,
                }
            )
    except Exception:
        db.session.rollback()
        rows = []

    if not rows and not os.path.exists(csv_path):
        return rows

    if not rows:
        try:
            with open(csv_path, 'r', encoding='utf-8') as fh:
                reader = csv.DictReader(fh)
                for idx, row in enumerate(reader, start=1):
                    if idx > 10:
                        break
                    activity_raw = row.get('activity_score') or row.get('Activity score') or ''
                    mut_raw = (
                        row.get('total_mutations')
                        or row.get('Total Mutations vs WT')
                        or row.get('protein_mutations')
                        or row.get('Protein muts')
                        or ''
                    )
                    try:
                        activity_value = float(str(activity_raw).strip())
                    except Exception:
                        activity_value = None
                    mutation_count = None
                    if str(mut_raw).strip():
                        try:
                            mutation_count = int(float(str(mut_raw).strip()))
                        except Exception:
                            mutation_count = None

                    rows.append(
                        {
                            'rank': idx,
                            'generation_number': row.get('generation_number') or row.get('Gen') or '',
                            'variant_index': row.get('plasmid_variant_index') or row.get('Variant') or '',
                            'activity_score': (
                                f'{activity_value:.3f}' if activity_value is not None else (activity_raw or '')
                            ),
                            'activity_score_value': activity_value,
                            'protein_mutations': mutation_count,
                            'variant_id': None,
                            'is_mutant': mutation_count is not None and mutation_count > 0,
                            'qc_flagged': False,
                        }
                    )
        except Exception:
            return []

    if any(row.get('variant_id') is None for row in rows):
        keys = []
        for row in rows:
            try:
                gen_num = int(str(row['generation_number']).strip())
                var_idx = str(row['variant_index']).strip()
                keys.append((gen_num, var_idx))
            except Exception:
                continue

        if not keys:
            return rows

        clauses = []
        params = {'eid': experiment_id}
        for i, (gen_num, var_idx) in enumerate(keys):
            clauses.append(f'(g.generation_number = :g{i} AND v.plasmid_variant_index = :v{i})')
            params[f'g{i}'] = gen_num
            params[f'v{i}'] = var_idx

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
                (int(row['generation_number']), str(row['plasmid_variant_index'])): int(row['variant_id'])
                for row in found
            }
            for row in rows:
                try:
                    key = (int(str(row['generation_number']).strip()), str(row['variant_index']).strip())
                    row['variant_id'] = id_map.get(key)
                except Exception:
                    row['variant_id'] = None
        except Exception:
            db.session.rollback()
            for row in rows:
                row['variant_id'] = None

    qc_path = os.path.join(
        os.path.dirname(csv_path),
        'stage4_qc_debug.csv',
    )
    if os.path.exists(qc_path):
        qc_by_variant = {}
        try:
            with open(qc_path, 'r', encoding='utf-8') as fh:
                reader = csv.DictReader(fh)
                for rec in reader:
                    vid_raw = rec.get('variant_id')
                    if vid_raw is None:
                        continue
                    try:
                        vid = int(str(vid_raw).strip())
                    except Exception:
                        continue
                    qc_stage4 = (rec.get('qc_stage4') or '').strip()
                    qc_by_variant[vid] = qc_stage4
        except Exception:
            qc_by_variant = {}

        if qc_by_variant:
            for row in rows:
                vid = row.get('variant_id')
                if not vid:
                    continue
                qc_note = qc_by_variant.get(int(vid), '')
                if qc_note and qc_note.lower() != 'ok':
                    row['qc_flagged'] = True
                    row['qc_note'] = qc_note
                else:
                    row['qc_note'] = qc_note or 'ok'

    return rows


def load_kpis(experiment_id):
    """Load high-level KPI metrics for staging workspace."""
    kpi = {
        'total_records': 0,
        'generations_covered': None,
        'activity_mean': None,
        'activity_median': None,
        'activity_best': None,
        'mutated_percent': None,
        'most_common_mutations': None,
        'syn_non_syn_ratio': None,
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
            {'eid': experiment_id},
        ).scalar()
        kpi['total_records'] = int(total_records or 0)

        gen_row = db.session.execute(
            text(
                """
                SELECT MIN(generation_number) AS min_gen, MAX(generation_number) AS max_gen
                FROM generations
                WHERE experiment_id = :eid
                """
            ),
            {'eid': experiment_id},
        ).fetchone()
        if gen_row and gen_row[0] is not None and gen_row[1] is not None:
            kpi['generations_covered'] = f"G{int(gen_row[0])} to G{int(gen_row[1])}"

        activity_row = db.session.execute(
            text(
                f"""
                WITH latest_activity AS (
                  {LATEST_ACTIVITY_SCORE_SQL}
                )
                SELECT AVG(la.activity_score) AS mean_score, MAX(la.activity_score) AS best_score
                FROM latest_activity la
                JOIN variants v ON v.variant_id = la.variant_id
                JOIN generations g ON g.generation_id = v.generation_id
                WHERE g.experiment_id = :eid
                """
            ),
            {'eid': experiment_id},
        ).fetchone()
        if activity_row:
            if activity_row[0] is not None:
                kpi['activity_mean'] = float(activity_row[0])
            if activity_row[1] is not None:
                kpi['activity_best'] = float(activity_row[1])

        activity_median = db.session.execute(
            text(
                f"""
                WITH latest_activity AS (
                  {LATEST_ACTIVITY_SCORE_SQL}
                )
                SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY la.activity_score)
                FROM latest_activity la
                JOIN variants v ON v.variant_id = la.variant_id
                JOIN generations g ON g.generation_id = v.generation_id
                WHERE g.experiment_id = :eid
                """
            ),
            {'eid': experiment_id},
        ).scalar()
        if activity_median is not None:
            kpi['activity_median'] = float(activity_median)

        analysed_count = db.session.execute(
            text(
                f"""
                WITH latest_vsa AS (
                  {LATEST_SUCCESS_VSA_SQL}
                )
                SELECT COUNT(*) AS analysed_variants
                FROM latest_vsa
                WHERE status = 'success'
                """
            ),
            {'eid': experiment_id},
        ).scalar()
        mut_count = db.session.execute(
            text(
                f"""
                WITH latest_vsa AS (
                  {LATEST_SUCCESS_VSA_SQL}
                )
                SELECT COUNT(*) AS mutated_variants
                FROM latest_vsa
                WHERE status = 'success'
                  AND COALESCE(
                    CAST(NULLIF(qc_flags->'mutation_counts'->>'nonsynonymous', '') AS integer),
                    0
                  ) > 0
                """
            ),
            {'eid': experiment_id},
        ).scalar()
        analysed = int(analysed_count or 0)
        mutated = int(mut_count or 0)
        if analysed > 0:
            kpi['mutated_percent'] = round((mutated / analysed) * 100.0, 1)

        top_mut_rows = db.session.execute(
            text(
                f"""
                WITH latest_vsa AS (
                  {LATEST_SUCCESS_VSA_SQL}
                )
                SELECT
                  CONCAT(m.original, m.position::text, m.mutated) AS mutation_label,
                  COUNT(*) AS mutation_count
                FROM mutations m
                JOIN latest_vsa lv ON lv.variant_id = m.variant_id
                JOIN variants v ON v.variant_id = m.variant_id
                JOIN generations g ON g.generation_id = v.generation_id
                WHERE g.experiment_id = :eid
                  AND lv.status = 'success'
                  AND m.mutation_type = 'protein'
                  AND m.is_synonymous = FALSE
                  AND m.original IS NOT NULL
                  AND m.mutated IS NOT NULL
                  AND m.position IS NOT NULL
                GROUP BY mutation_label
                ORDER BY mutation_count DESC, mutation_label
                LIMIT 3
                """
            ),
            {'eid': experiment_id},
        ).mappings().all()
        if top_mut_rows:
            kpi['most_common_mutations'] = ', '.join(
                f"{str(r['mutation_label'])} ({int(r['mutation_count'])})" for r in top_mut_rows
            )

        syn_non_syn = db.session.execute(
            text(
                f"""
                WITH latest_vsa AS (
                  {LATEST_SUCCESS_VSA_SQL}
                ),
                latest_syn AS (
                  {LATEST_SYNONYMOUS_COUNTS_SQL}
                ),
                latest_non_syn AS (
                  {LATEST_NONSYNONYMOUS_COUNTS_SQL}
                )
                SELECT
                  COALESCE(SUM(ls.syn_count), 0) AS syn_count,
                  COALESCE(SUM(ln.non_syn_count), 0) AS non_syn_count
                FROM generations g
                LEFT JOIN variants v ON v.generation_id = g.generation_id
                LEFT JOIN latest_vsa lv ON lv.variant_id = v.variant_id
                LEFT JOIN latest_syn ls ON ls.variant_id = v.variant_id
                LEFT JOIN latest_non_syn ln ON ln.variant_id = v.variant_id
                WHERE g.experiment_id = :eid
                  AND lv.status = 'success'
                """
            ),
            {'eid': experiment_id},
        ).mappings().first()
        if syn_non_syn:
            syn_count = int(syn_non_syn['syn_count'] or 0)
            non_syn_count = int(syn_non_syn['non_syn_count'] or 0)
            if syn_count > 0 or non_syn_count > 0:
                if non_syn_count > 0:
                    kpi['syn_non_syn_ratio'] = f"{syn_count}:{non_syn_count} ({(syn_count / non_syn_count):.2f})"
                else:
                    kpi['syn_non_syn_ratio'] = f"{syn_count}:0"
    except Exception:
        db.session.rollback()
        return kpi

    return kpi


def infer_scoring_metadata(qc_csv_path):
    """Infer baseline/scoring mode from Stage 4 QC CSV schema."""
    if not qc_csv_path or not os.path.exists(qc_csv_path):
        return {
            'baseline_used': 'pending',
            'scoring_method': 'pending',
        }

    try:
        with open(qc_csv_path, 'r', encoding='utf-8') as fh:
            reader = csv.reader(fh)
            header = next(reader, [])
        cols = {str(c).strip() for c in header if c}
    except Exception:
        return {
            'baseline_used': 'unknown',
            'scoring_method': 'activity_score ratio',
        }

    if {'dna_med', 'prot_med'}.issubset(cols):
        return {
            'baseline_used': 'Generation median=1.0',
            'scoring_method': 'Fallback ratio (DNA_norm/Protein_norm)',
        }

    if {'dna_yield_norm', 'protein_yield_norm', 'activity_score'}.issubset(cols):
        return {
            'baseline_used': 'WT=1.0',
            'scoring_method': 'WT-normalized ratio',
        }

    return {
        'baseline_used': 'unknown',
        'scoring_method': 'activity_score ratio',
    }
