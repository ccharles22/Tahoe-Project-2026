"""
Compatibility adapter for legacy staging imports.

Wraps the canonical UniProt service (``app.services.sequence.uniprot_service``)
in a dict-shaped interface expected by older staging route code.

Canonical implementation lives in:
    app.services.sequence.uniprot_service
"""

from app.services.sequence.uniprot_service import (
    UniProtRetrievalError,
    acquire_uniprot_entry_with_features,
)


class UniprotServiceError(Exception):
    """Legacy error type kept for compatibility with older route code."""


class UniprotService:
    """Legacy dict-based UniProt client kept for backward compatibility."""

    @staticmethod
    def fetch(accession: str) -> dict:
        """Fetch a UniProt entry and return a flat dictionary.

        Delegates to the canonical ``acquire_uniprot_entry_with_features``
        and re-shapes the result into the dict format expected by older
        staging templates.

        Args:
            accession: UniProt accession string.

        Returns:
            dict with keys: sequence, protein_length, features,
            protein_name, organism.

        Raises:
            UniprotServiceError: On any retrieval failure.
        """
        try:
            entry = acquire_uniprot_entry_with_features(accession)
        except UniProtRetrievalError as exc:
            raise UniprotServiceError(str(exc)) from exc

        features = [
            {
                "type": f.feature_type,
                "description": f.description or "",
                "start": f.begin,
                "end": f.end,
            }
            for f in entry.features
        ]

        return {
            "sequence": entry.sequence,
            "protein_length": entry.length,
            "features": features,
            "protein_name": entry.protein_name,
            "organism": entry.organism,
        }
