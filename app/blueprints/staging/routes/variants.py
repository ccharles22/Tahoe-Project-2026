"""Variant detail and per-variant export endpoints."""

import csv
import io
import os

from flask import Response, current_app, jsonify, render_template, url_for
from flask_login import current_user, login_required
from sqlalchemy import text

from app.extensions import db

from .. import staging_bp
from .ownership import get_owned_variant_or_none


def _load_stage4_qc_for_variant(experiment_id: int, variant_id: int) -> str:
    qc_path = os.path.join(
        current_app.root_path,
        'static',
        'generated',
        str(int(experiment_id)),
        'stage4_qc_debug.csv',
    )
    if not os.path.exists(qc_path):
        return ''
    try:
        with open(qc_path, 'r', encoding='utf-8') as fh:
            reader = csv.DictReader(fh)
            for rec in reader:
                try:
                    rec_variant_id = int(str(rec.get('variant_id', '')).strip())
                except Exception:
                    continue
                if rec_variant_id != int(variant_id):
                    continue
                return (rec.get('qc_stage4') or '').strip()
    except Exception:
        return ''
    return ''


def _load_variant_payload(variant_id: int):
    """Build enriched variant payload for drawer and detail page."""
    row = get_owned_variant_or_none(variant_id)
    if not row:
        return None

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
        {'vid': variant_id, 'uid': int(current_user.user_id)},
    ).mappings().first()

    mutations = []
    snippet = ''
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
            {'aid': int(latest_analysis['analysis_id'])},
        ).mappings().all()

        for m in mut_rows:
            mutations.append(
                {
                    'mutation_type': m['mutation_type'] or '',
                    'aa_position': m['aa_position_1based'],
                    'codon_index': m['codon_index_1based'],
                    'wt_aa': m['wt_aa'] or '',
                    'var_aa': m['var_aa'] or '',
                    'wt_codon': m['wt_codon'] or '',
                    'var_codon': m['var_codon'] or '',
                    'notes': m['notes'] or '',
                }
            )

    protein_seq = (row['protein_sequence'] or '').strip()
    if protein_seq and mutations:
        first_pos = mutations[0].get('aa_position')
        if isinstance(first_pos, int) and first_pos > 0:
            idx0 = first_pos - 1
            left = max(0, idx0 - 10)
            right = min(len(protein_seq), idx0 + 11)
            snippet = protein_seq[left:right]

    yields_row = db.session.execute(
        text(
            """
            SELECT
              MAX(CASE WHEN metric_name = 'dna_yield' THEN value END) AS dna_yield,
              MAX(CASE WHEN metric_name = 'protein_yield' THEN value END) AS protein_yield
            FROM metrics
            WHERE variant_id = :vid
              AND metric_type = 'raw'
              AND metric_name IN ('dna_yield', 'protein_yield')
            """
        ),
        {'vid': int(variant_id)},
    ).mappings().first()
    dna_yield = yields_row['dna_yield'] if yields_row else None
    protein_yield = yields_row['protein_yield'] if yields_row else None

    qc_note = _load_stage4_qc_for_variant(int(row['experiment_id']), int(variant_id))
    if not qc_note:
        qc_note = 'pending'

    return {
        'variant_id': int(row['variant_id']),
        'variant_index': row['plasmid_variant_index'] or '',
        'generation_number': int(row['generation_number']) if row['generation_number'] is not None else None,
        'parent_variant_id': row['parent_variant_id'],
        'activity_score': float(row['activity_score']) if row['activity_score'] is not None else None,
        'dna_yield': float(dna_yield) if dna_yield is not None else None,
        'protein_yield': float(protein_yield) if protein_yield is not None else None,
        'qc_note': qc_note,
        'protein_snippet': snippet,
        'mutations': mutations,
        'download_urls': {
            'dna_fasta': url_for('staging.download_variant_dna_fasta', variant_id=int(row['variant_id'])),
            'protein_fasta': url_for('staging.download_variant_protein_fasta', variant_id=int(row['variant_id'])),
            'mutation_csv': url_for('staging.download_variant_mutation_csv', variant_id=int(row['variant_id'])),
        },
        'full_variant_url': url_for('staging.variant_page', variant_id=int(row['variant_id'])),
    }


@staging_bp.get('/variant/<int:variant_id>/details')
@login_required
def variant_details(variant_id: int):
    """Return variant details, latest mutation calls, and export URLs."""
    payload = _load_variant_payload(variant_id)
    if payload is None:
        return jsonify({'error': 'Variant not found'}), 404
    return jsonify(payload)


@staging_bp.get('/variant/<int:variant_id>')
@login_required
def variant_page(variant_id: int):
    """Render a full-page variant detail view."""
    payload = _load_variant_payload(variant_id)
    if payload is None:
        return Response('Variant not found.', status=404)
    return render_template('staging/variant_detail.html', variant=payload)


@staging_bp.get('/variant/<int:variant_id>/download/dna_fasta')
@login_required
def download_variant_dna_fasta(variant_id: int):
    """Download assembled DNA sequence for a variant in FASTA format."""
    row = get_owned_variant_or_none(variant_id)
    if not row:
        return Response('Variant not found.', status=404)

    dna = (row['assembled_dna_sequence'] or '').strip()
    if not dna:
        return Response('DNA sequence not available.', status=404)

    fasta = f'>variant_{variant_id}_dna\n'
    for i in range(0, len(dna), 70):
        fasta += dna[i : i + 70] + '\n'

    resp = Response(fasta, mimetype='application/x-fasta')
    resp.headers['Content-Disposition'] = f'attachment; filename=variant_{variant_id}_dna.fasta'
    return resp


@staging_bp.get('/variant/<int:variant_id>/download/protein_fasta')
@login_required
def download_variant_protein_fasta(variant_id: int):
    """Download translated protein sequence for a variant in FASTA format."""
    row = get_owned_variant_or_none(variant_id)
    if not row:
        return Response('Variant not found.', status=404)

    protein = (row['protein_sequence'] or '').strip()
    if not protein:
        return Response('Protein sequence not available. Run sequence processing first.', status=404)

    fasta = f'>variant_{variant_id}_protein\n'
    for i in range(0, len(protein), 70):
        fasta += protein[i : i + 70] + '\n'

    resp = Response(fasta, mimetype='application/x-fasta')
    resp.headers['Content-Disposition'] = f'attachment; filename=variant_{variant_id}_protein.fasta'
    return resp


@staging_bp.get('/variant/<int:variant_id>/download/mutation_csv')
@login_required
def download_variant_mutation_csv(variant_id: int):
    """Download latest mutation calls for a variant as CSV."""
    row = get_owned_variant_or_none(variant_id)
    if not row:
        return Response('Variant not found.', status=404)

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
        {'vid': variant_id, 'uid': int(current_user.user_id)},
    ).scalar()
    if not latest_analysis:
        return Response('No mutation analysis available. Run sequence processing first.', status=404)

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
        {'aid': int(latest_analysis)},
    ).mappings().all()

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(
        [
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
    for m in mut_rows:
        writer.writerow(
            [
                m['mutation_type'],
                m['codon_index_1based'],
                m['aa_position_1based'],
                m['wt_codon'],
                m['var_codon'],
                m['wt_aa'],
                m['var_aa'],
                m['notes'],
            ]
        )

    resp = Response(out.getvalue(), mimetype='text/csv')
    resp.headers['Content-Disposition'] = f'attachment; filename=variant_{variant_id}_mutations.csv'
    return resp
