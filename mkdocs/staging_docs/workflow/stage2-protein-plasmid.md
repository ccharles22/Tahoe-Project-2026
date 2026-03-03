# Stage 2: Protein Selection & Plasmid Validation

Stage 2 initializes an experiment from a user-chosen wild-type (WT) protein. You first select a WT using a UniProt accession, then upload the corresponding plasmid FASTA. The portal validates that the WT protein is encoded within the plasmid sequence, including cases where the coding region wraps around the origin due to plasmid circularity.

## What you need before you start

- A **UniProt accession** for your WT protein (e.g., `O34996`).
- A **single-record plasmid FASTA** file containing the full plasmid DNA sequence.

## Step 1 — Fetch the WT from UniProt

1. Go to **Workspace → Staging**.
2. In **Stage 02: Fetch WT (UniProt)**, enter your **UniProt accession** and submit.
3. After submission, you will be redirected back to the staging page and a status message will confirm success or explain any error.

What happens next:
- The portal fetches the WT **amino acid sequence** and **feature annotations** (e.g., domains) from UniProt and stores them for your experiment.
- A **placeholder plasmid CDS** may be generated via back-translation so you can proceed even before uploading your real plasmid. This placeholder is stored under the experiment and is designed to be overwritten in Step 2.

Notes:
- WT protein records are managed by `uniprot_id` to avoid duplication, but your experiment's plasmid sequence is stored **per experiment**, not on the shared WT record.
- If you re-fetch a WT for an existing experiment, dependent sequence-processing outputs are marked **stale** so later stages don't reuse results computed with older inputs.

## Step 2 — Upload plasmid FASTA and validate

1. In **Stage 02b: Upload plasmid FASTA**, choose your plasmid FASTA file and submit.
2. The portal parses your FASTA and validates the plasmid.
3. You will be redirected back to the staging page with a PASS/FAIL message and a technical details panel.

### FASTA parsing rules

Your file must meet these requirements:
- **Single-record FASTA** (one `>` header and one sequence).
- UTF-8 decodable text.
- Whitespace is ignored; sequence is normalised (`U → T`).
- Bases must be within the extended IUPAC DNA alphabet: `ACGTNRYWSKMBDHV`.

If the file does not meet these requirements, validation is rejected with an error message rather than silently altering the input.

### Validation logic (high level)

Validation checks whether the WT protein can be found encoded within the plasmid DNA:
- Treats plasmids as **circular** using a doubled search space (`S+S`).
- Checks both **forward** and **reverse-complement** strands.
- Translates **all six reading frames** (3 forward + 3 reverse).
- Uses a shared default translation table: `DEFAULT_GENETIC_CODE_TABLE = 11`.
- Attempts an **exact match first**:
  - If found → PASS (100% identity, full coverage).
- If no exact match is found:
  - Performs a **local alignment** to find the best approximate hit.
  - With the current default (`require_exact=True`), approximate hits are reported but still **fail** validation.

!!! warning "Strict mode note"
    With `require_exact=True`, any amino-acid mismatches between the translated plasmid hit and the WT sequence will cause validation to fail, even if the alignment is otherwise strong.

### What you see after validation

The staging page shows:
- **PASS/FAIL**
- **Identity** and **coverage**
- **Strand**
- **Start/end coordinates**
- **wraps** flag (whether the coding region crosses the plasmid origin)
- **genetic_code_used** (translation table used)

Definitions:
- **Identity** = percentage of amino-acid positions that match within the best hit.
- **Coverage** = proportion of the WT protein length covered by the best hit.

Coordinate semantics:
- `start_nt` is **0-based**
- `end_nt` is **0-based inclusive**
- `wraps=True` indicates the region crosses the origin (wrap-around)

### Persistence and reproducibility

Each validation run is cached for fast page rendering and also saved to the database so results persist across sessions and can be audited later:
- A compact validation payload is cached in the user session (for quick UI display).
- A **database record** (`StagingValidation`, one row per run) stores:
  - `is_valid`, `identity`, `coverage`, `strand`, `start_nt`, `end_nt`, `wraps`
  - `failure_reason`, `genetic_code_used`, `created_at`

## Troubleshooting

**"FASTA invalid" or parsing error**
- Ensure your FASTA contains **one record only**
- Confirm it starts with `>` and contains only allowed DNA/IUPAC characters
- Remove additional sequences/records

**Validation fails but plasmid is expected to be correct**
- The validator is conservative by default (`require_exact=True`), so small differences can fail validation.
- Check whether your construct differs from the UniProt WT (mutations, tags, truncations, alternative start sites).
- Confirm your plasmid sequence is complete and not missing the coding region.

**wraps=True**
- This is expected for circular plasmids when the gene crosses the origin. The portal handles this case explicitly.

## Design decisions (why it works this way)

- **Shared WT, per-experiment plasmid:** WT proteins are keyed by `uniprot_id` to avoid duplication, while plasmids are stored per experiment so experiments can override plasmid inputs safely.
- **Strict FASTA rules:** prevents silent data corruption that would compromise downstream mutation calling and activity analysis.
- **Circular + 6-frame validation:** supports common real plasmid cases (orientation changes, wrap-around, unknown frame).
- **Genetic code consistency:** the validator uses the same default translation table as the rest of the pipeline and records `genetic_code_used` for transparency.
- **Persisted validation history:** storing each run in the DB supports auditability and reproducibility.

## Limitations and future improvements

- **Conservative default (`require_exact=True`):** approximate matches from alignment still fail; a future "tolerant mode" could accept near-matches using explicit identity/coverage thresholds.
- **UniProt features are not refreshed:** features are inserted only if missing; a refresh strategy could propagate UniProt annotation updates.
- **API access control consistency:** staging routes enforce login/ownership; experiment-linked API endpoints should apply the same scoping for consistent data segregation.
- **Coordinate interpretation:** coordinates are precise (0-based/inclusive) but easy to misread; adding an optional 1-based "human view" could reduce confusion.

