# Sequence Service

Core sequence processing functions for WT mapping, variant extraction, and mutation calling.

::: app.services.sequence.sequence_service
    options:
      members:
        - WTMapping
        - QCFlags
        - VariantSeqResult
        - MutationRecord
        - MutationCounts
        - map_wt_gene_in_plasmid
        - process_variant_plasmid
        - call_mutations_against_wt
        - call_indels_via_protein_alignment
