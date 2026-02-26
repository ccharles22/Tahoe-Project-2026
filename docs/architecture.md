# Architecture

## Pipeline Flow

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────────┐
│  Flask Route /   │────▸│  submit_     │────▸│ run_sequence_    │
│  CLI __main__    │     │  sequence_   │     │ processing()     │
│                  │     │  processing()│     │ (background      │
└─────────────────┘     └──────────────┘     │  thread)         │
                                              └────────┬─────────┘
                                                       │
                        ┌──────────────────────────────┘
                        ▼
              ┌─────────────────────┐
              │  1. Load WT refs    │  db_repo.get_wt_reference()
              │  2. Map WT gene     │  sequence_service.map_wt_gene_in_plasmid()
              │  3. Cache mapping   │  db_repo.upsert_wt_mapping()
              └────────┬────────────┘
                       │
                       ▼
              ┌─────────────────────┐
              │  For each variant:  │
              │  a. Extract CDS     │  process_variant_plasmid()
              │  b. Call mutations   │  call_mutations_against_wt()
              │  c. Batch persist   │  db_repo.insert_variant_analyses_batch()
              └────────┬────────────┘
                       │
                       ▼
              ┌─────────────────────┐
              │  Final status       │  ANALYSED / ANALYSED_WITH_ERRORS / FAILED
              └─────────────────────┘
```

## Mutation Calling Strategy

The pipeline selects a mutation calling strategy based on sequence characteristics:

| Condition | Strategy | Rationale |
|-----------|----------|-----------|
| CDS not divisible by 3 | `FRAMESHIFT` record | Cannot align codons |
| WT and variant same length | Codon-by-codon comparison | Fast, exact |
| Different lengths (both in-frame) | Protein alignment (BLOSUM62) | Handles indels |

## Key Design Decisions

- **Frame offset in coordinates**: The reading frame (0, 1, or 2) is incorporated
  into `cds_start_0based` / `cds_end_0based_excl` during WT mapping, so variant
  processing does not apply any additional frame trimming.

- **Cached aligners**: BLOSUM62 matrix and `PairwiseAligner` instances are loaded
  once at module level to avoid repeated disk I/O.

- **Structured alignment parsing**: Uses `aln.aligned` coordinate blocks instead
  of `aln.format()` text output, which is fragile across Biopython versions.

- **QC-aware status**: Final experiment status is `ANALYSED_WITH_ERRORS` if any
  variant has a frameshift, premature stop, missing protein, or processing exception.
