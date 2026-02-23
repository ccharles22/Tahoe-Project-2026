"""Experiment-level CSV export endpoints."""

import csv
import io

from flask import Response
from flask_login import current_user, login_required
from sqlalchemy import text

from app.extensions import db

from .. import staging_bp
from .ownership import experiment_owned_by_current_user


@staging_bp.get('/experiment/<int:experiment_id>/download/results_csv')
@login_required
def download_experiment_results_csv(experiment_id: int):
    """Download experiment variant rows and key metrics as CSV."""
    if not experiment_owned_by_current_user(experiment_id):
        return Response('Experiment not found.', status=404)

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
        {'eid': experiment_id},
    ).mappings().all()

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            'experiment_id',
            'generation_number',
            'variant_id',
            'parent_variant_id',
            'plasmid_variant_index',
            'assembled_dna_sequence',
            'protein_sequence',
            'dna_yield',
            'protein_yield',
            'activity_score',
        ]
    )
    for r in rows:
        writer.writerow(
            [
                experiment_id,
                r['generation_number'],
                r['variant_id'],
                r['parent_variant_id'],
                r['plasmid_variant_index'],
                r['assembled_dna_sequence'],
                r['protein_sequence'],
                r['dna_yield'],
                r['protein_yield'],
                r['activity_score'],
            ]
        )

    resp = Response(out.getvalue(), mimetype='text/csv')
    resp.headers['Content-Disposition'] = f'attachment; filename=experiment_{experiment_id}_results.csv'
    return resp


@staging_bp.get('/experiment/<int:experiment_id>/download/mutation_report_csv')
@login_required
def download_experiment_mutation_report_csv(experiment_id: int):
    """Download experiment mutation-level report as CSV."""
    if not experiment_owned_by_current_user(experiment_id):
        return Response('Experiment not found.', status=404)

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
        {'eid': experiment_id, 'uid': int(current_user.user_id)},
    ).mappings().all()

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
            'experiment_id',
            'generation_number',
            'variant_id',
            'plasmid_variant_index',
            'parent_variant_id',
            'analysis_id',
            'analysed_at',
            'mutation_type',
            'codon_index_1based',
            'aa_position_1based',
            'wt_codon',
            'var_codon',
            'wt_aa',
            'var_aa',
            'notes',
        ]
    )
    for r in rows:
        writer.writerow(
            [
                experiment_id,
                r['generation_number'],
                r['variant_id'],
                r['plasmid_variant_index'],
                r['parent_variant_id'],
                r['analysis_id'],
                r['analysed_at'],
                r['mutation_type'],
                r['codon_index_1based'],
                r['aa_position_1based'],
                r['wt_codon'],
                r['var_codon'],
                r['wt_aa'],
                r['var_aa'],
                r['notes'],
            ]
        )

    resp = Response(out.getvalue(), mimetype='text/csv')
    resp.headers['Content-Disposition'] = f'attachment; filename=experiment_{experiment_id}_mutation_report.csv'
    return resp
