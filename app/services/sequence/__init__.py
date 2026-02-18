"""
Sequence processing service layer.

Modules:
    db_repo             – Database repository (CRUD for variants, mutations, metrics)
    sequence_service    – Core biology logic (WT mapping, CDS extraction, mutation calling)
    uniprot_service     – UniProt REST API client with retry logic
"""
