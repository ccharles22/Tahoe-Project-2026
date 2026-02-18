"""
Compatibility adapter for legacy staging imports.

Canonical UniProt implementation lives in:
    app.services.uniprot_service
"""

from app.services.uniprot_service import (
    UniProtRetrievalError,
    acquire_uniprot_entry_with_features,
)


class UniprotServiceError(Exception):
    """Legacy error type kept for compatibility with older route code."""


class UniprotService:
    @staticmethod
    def fetch(accession: str) -> dict:
        """
        Legacy dict-shaped response backed by the canonical UniProt service.
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
