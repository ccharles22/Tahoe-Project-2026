"""WT and plasmid ingestion endpoints for staging."""

from flask import redirect, request, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Experiment, ProteinFeature, WildtypeProtein
from app.services.sequence import db_repo as sequence_db_repo
from app.services.sequence.uniprot_service import (
    UniProtRetrievalError,
    acquire_uniprot_entry_with_features,
)
from app.services.staging.backtranslate import backtranslate
from app.services.staging.parse_fasta import parse_fasta
from app.services.staging.plasmid_validator import validate_plasmid
from app.services.staging.session_state import (
    clear_validation_from_session,
    clear_sequence_status_from_session,
    mark_sequence_reprocess_required,
    save_validation_to_session,
)

from .. import staging_bp


def _merge_extra_metadata(exp: Experiment, updates: dict) -> None:
    """Merge JSON-serialisable fields into experiment.extra_metadata."""
    meta = exp.extra_metadata if isinstance(exp.extra_metadata, dict) else {}
    merged = dict(meta)
    merged.update(updates)
    exp.extra_metadata = merged


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

    accession = entry.accession
    sequence = entry.sequence
    protein_length = entry.length
    features = entry.features
    placeholder_plasmid = backtranslate(sequence)

    wt = WildtypeProtein.query.filter_by(uniprot_id=accession).first()
    if wt:
        # Preserve existing plasmid row data to avoid cross-experiment/user overwrites.
        # Canonical UniProt sequence fields are deterministic and safe to refresh.
        wt.amino_acid_sequence = sequence
        wt.sequence_length = protein_length
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
        exp = Experiment.query.filter_by(
            experiment_id=int(experiment_id),
            user_id=current_user.user_id,
        ).first()
        if not exp:
            return redirect(
                url_for(
                    'staging.create_experiment',
                    wt_message='Experiment not found or you do not have access.',
                )
            )
        previous_accession = (
            exp.wt.uniprot_id.strip().upper()
            if getattr(exp, 'wt', None) and getattr(exp.wt, 'uniprot_id', None)
            else ''
        )
        exp.wt_id = wt.wt_id
        protein_name = entry.protein_name
        if protein_name and (not exp.name or exp.name.startswith('Experiment ')):
            exp.name = f'{protein_name} ({accession})'
    else:
        previous_accession = ''
        protein_name = entry.protein_name
        exp = Experiment(
            user_id=current_user.user_id,
            wt_id=wt.wt_id,
            name=experiment_name or (f'{protein_name} ({accession})' if protein_name else f'Experiment ({accession})'),
        )
        db.session.add(exp)
        db.session.flush()
        experiment_id = str(exp.experiment_id)

    # Persist experiment-scoped plasmid so uploads do not overwrite shared WT rows.
    # Reset to placeholder when the accession changed for an existing experiment.
    exp_meta_updates = {'wt_uniprot_accession': accession}
    if previous_accession != accession or not (exp.extra_metadata or {}).get('wt_plasmid_sequence'):
        exp_meta_updates['wt_plasmid_sequence'] = placeholder_plasmid
    _merge_extra_metadata(exp, exp_meta_updates)

    should_refresh_features = (
        ProteinFeature.query.filter_by(wt_id=wt.wt_id).first() is None
    )
    if should_refresh_features:
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
    exp_id_int = int(experiment_id)
    sync_warning = None
    try:
        sequence_db_repo.upsert_uniprot_staging(
            db.engine,
            exp_id_int,
            int(current_user.user_id),
            accession,
            sequence,
            overwrite=True,
        )
        sequence_db_repo.clear_wt_mapping_cache(db.engine, exp_id_int)
    except Exception as exc:
        sync_warning = (
            "Fetched WT sequence, but failed to sync sequence-processing metadata: "
            f"{exc}"
        )
    clear_sequence_status_from_session(experiment_id)
    mark_sequence_reprocess_required(experiment_id)
    if previous_accession and previous_accession != accession:
        clear_validation_from_session(experiment_id)

    return redirect(
        url_for(
            'staging.create_experiment',
            experiment_id=experiment_id,
            wt_message=sync_warning or 'Fetched WT sequence + features successfully.',
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
    exp = Experiment.query.filter_by(experiment_id=exp_id_int, user_id=current_user.user_id).first()
    if not exp:
        return redirect(
            url_for(
                'staging.create_experiment',
                wt_message='Experiment not found or you do not have access.',
            )
        )
    if not exp.wt_id:
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

    _merge_extra_metadata(exp, {'wt_plasmid_sequence': dna, 'wt_uniprot_accession': wt.uniprot_id})

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

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        return redirect(
            url_for(
                'staging.create_experiment',
                experiment_id=experiment_id,
                wt_message='Database error while saving plasmid upload.',
            )
        )
    cache_warning = None
    try:
        sequence_db_repo.clear_wt_mapping_cache(db.engine, exp_id_int)
    except Exception as exc:
        cache_warning = f'Plasmid validated, but WT mapping cache was not cleared: {exc}'
    clear_sequence_status_from_session(experiment_id)
    mark_sequence_reprocess_required(experiment_id)

    return redirect(
        url_for(
            'staging.create_experiment',
            experiment_id=experiment_id,
            wt_message=(
                cache_warning
                or ('Plasmid validated.' if result.is_valid else 'Plasmid invalid (see details).')
            ),
        )
    )
