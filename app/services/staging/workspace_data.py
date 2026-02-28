"""Workspace data loaders for staging UI panels and summaries."""

from __future__ import annotations

import csv
import os

from sqlalchemy import text

from app.extensions import db


def load_top10_rows(csv_path, experiment_id):
    """Load top-10 rows from generated CSV and attach variant ids when possible."""
    rows = []
    if not os.path.exists(csv_path):
        return rows

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
                try:
                    mutation_count = int(float(str(mut_raw).strip()))
                except Exception:
                    mutation_count = 0

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
                        'is_mutant': mutation_count > 0,
                        'qc_flagged': False,
                    }
                )
    except Exception:
        return []

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
                """
                SELECT AVG(m.value) AS mean_score, MAX(m.value) AS best_score
                FROM metrics m
                JOIN generations g ON g.generation_id = m.generation_id
                WHERE g.experiment_id = :eid
                  AND m.metric_name = 'activity_score'
                  AND m.metric_type = 'derived'
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
                """
                SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY m.value)
                FROM metrics m
                JOIN generations g ON g.generation_id = m.generation_id
                WHERE g.experiment_id = :eid
                  AND m.metric_name = 'activity_score'
                  AND m.metric_type = 'derived'
                """
            ),
            {'eid': experiment_id},
        ).scalar()
        if activity_median is not None:
            kpi['activity_median'] = float(activity_median)

        analysed_count = db.session.execute(
            text(
                """
                SELECT COUNT(DISTINCT variant_id)
                FROM variant_sequence_analysis
                WHERE experiment_id = :eid
                """
            ),
            {'eid': experiment_id},
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
            {'eid': experiment_id},
        ).scalar()
        analysed = int(analysed_count or 0)
        mutated = int(mut_count or 0)
        if analysed > 0:
            kpi['mutated_percent'] = round((mutated / analysed) * 100.0, 1)

        top_mut_rows = db.session.execute(
            text(
                """
                WITH latest AS (
                  SELECT variant_id, MAX(analysis_id) AS analysis_id
                  FROM variant_sequence_analysis
                  WHERE experiment_id = :eid
                  GROUP BY variant_id
                )
                SELECT
                  CONCAT(vm.wt_aa, vm.aa_position_1based::text, vm.var_aa) AS mutation_label,
                  COUNT(*) AS mutation_count
                FROM variant_mutations vm
                JOIN latest l ON l.analysis_id = vm.analysis_id
                WHERE vm.wt_aa IS NOT NULL
                  AND vm.var_aa IS NOT NULL
                  AND vm.aa_position_1based IS NOT NULL
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
                """
                WITH latest AS (
                  SELECT variant_id, MAX(analysis_id) AS analysis_id
                  FROM variant_sequence_analysis
                  WHERE experiment_id = :eid
                  GROUP BY variant_id
                )
                SELECT
                  SUM(
                    CASE
                      WHEN LOWER(COALESCE(vm.mutation_type, '')) LIKE '%synonymous%'
                           AND LOWER(COALESCE(vm.mutation_type, '')) NOT LIKE '%non%'
                      THEN 1 ELSE 0
                    END
                  ) AS syn_count,
                  SUM(
                    CASE
                      WHEN LOWER(COALESCE(vm.mutation_type, '')) LIKE '%non%synonymous%'
                           OR LOWER(COALESCE(vm.mutation_type, '')) IN ('missense', 'nonsense', 'frameshift')
                      THEN 1 ELSE 0
                    END
                  ) AS non_syn_count
                FROM variant_mutations vm
                JOIN latest l ON l.analysis_id = vm.analysis_id
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
