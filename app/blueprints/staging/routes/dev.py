"""Development-only helper endpoints for staging."""

from flask import Response
from flask_login import login_required

from app.models import Experiment, WildtypeProtein
from app.services.staging.backtranslate import backtranslate

from .. import staging_bp


@staging_bp.get('/dev/plasmid_fasta/<int:experiment_id>')
@login_required
def dev_plasmid_fasta(experiment_id: int):
    """Generate a downloadable back-translated FASTA for the experiment WT."""
    exp = Experiment.query.get(experiment_id)
    if not exp or not exp.wt_id:
        return Response('Experiment or WT not found.', status=404)

    wt = WildtypeProtein.query.get(exp.wt_id)
    if not wt or not wt.amino_acid_sequence:
        return Response('WT protein sequence not found for this experiment.', status=404)

    dna = backtranslate(wt.amino_acid_sequence)

    # Format as FASTA with standard 70-character line wrapping.
    fasta = f'>dev_plasmid_experiment_{experiment_id}\n'
    for i in range(0, len(dna), 70):
        fasta += dna[i:i + 70] + '\n'

    resp = Response(fasta, mimetype='application/x-fasta')
    resp.headers['Content-Disposition'] = f'attachment; filename=dev_plasmid_experiment_{experiment_id}.fasta'
    return resp
