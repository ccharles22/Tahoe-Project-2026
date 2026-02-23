"""WT and plasmid ingestion endpoints for staging."""

from flask import redirect, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Experiment, ProteinFeature, WildtypeProtein
from app.services.sequence.uniprot_service import (
    UniProtRetrievalError,
    acquire_uniprot_entry_with_features,
)
from app.services.staging.backtranslate import backtranslate
from app.services.staging.parse_fasta import parse_fasta
from app.services.staging.plasmid_validator import validate_plasmid
from app.services.staging.session_state import save_validation_to_session

from .. import staging_bp


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
        return redirect(
            url_for(
                'staging.create_experiment',
                experiment_id=experiment_id or '',
                wt_message=str(e),
            )
        )

    sequence = entry.sequence
    protein_length = entry.length
    features = entry.features
    placeholder_plasmid = backtranslate(sequence)

    wt = WildtypeProtein.query.filter_by(uniprot_id=accession).first()
    if wt:
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
        db.session.flush()

    if experiment_id and experiment_id.isdigit():
        exp = Experiment.query.get(int(experiment_id))
        if not exp:
            return redirect(url_for('staging.create_experiment', wt_message='Experiment not found'))
        exp.wt_id = wt.wt_id
        protein_name = entry.protein_name
        if protein_name and (not exp.name or exp.name.startswith('Experiment ')):
            exp.name = f'{protein_name} ({accession})'
    else:
        protein_name = entry.protein_name
        exp = Experiment(
            user_id=current_user.user_id,
            wt_id=wt.wt_id,
            name=experiment_name or (f'{protein_name} ({accession})' if protein_name else f'Experiment ({accession})'),
        )
        db.session.add(exp)
        db.session.flush()
        experiment_id = str(exp.experiment_id)

    ProteinFeature.query.filter_by(wt_id=wt.wt_id).delete()
    for feat in features:
        pf = ProteinFeature(
            wt_id=wt.wt_id,
            feature_type=feat.feature_type or 'unknown',
            description=feat.description or '',
            start_position=feat.begin or 0,
            end_position=feat.end or 0,
        )
        db.session.add(pf)

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return redirect(
            url_for(
                'staging.create_experiment',
                experiment_id=experiment_id or '',
                wt_message=f'Database error: {exc}',
            )
        )

    return redirect(
        url_for(
            'staging.create_experiment',
            experiment_id=experiment_id,
            wt_message='Fetched WT sequence + features successfully.',
        )
    )


@staging_bp.post('/plasmid')
@login_required
def upload_plasmid():
    """Upload and validate plasmid FASTA for an experiment."""
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

    wt.plasmid_sequence = dna

    if not wt.amino_acid_sequence:
        return redirect(
            url_for(
                'staging.create_experiment',
                experiment_id=experiment_id,
                wt_message='WT protein sequence missing. Fetch WT again.',
            )
        )

    result = validate_plasmid(wt.amino_acid_sequence, dna)
    save_validation_to_session(experiment_id, result)

    db.session.commit()

    return redirect(
        url_for(
            'staging.create_experiment',
            experiment_id=experiment_id,
            wt_message='Plasmid validated.' if result.is_valid else 'Plasmid invalid (see details).',
        )
    )
