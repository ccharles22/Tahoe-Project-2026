# Step 3: Upload Data

Upload your variant data file containing DNA sequences and measurements from your directed evolution experiment.

## Overview

This step:

- Accepts TSV, CSV, or JSON files
- Parses variant records with DNA sequences and measurements
- Validates data integrity and structure
- Creates variant and generation records in the database
- Reports warnings for data quality issues

## Prerequisites

- ✅ **Completed Step 1** (Fetch Wild-Type)
- 📄 A data file (TSV, CSV, or JSON) with variant information

## Required Data Fields

Your file must include these fields:

| Field | Type | Description |
|-------|------|-------------|
| `variant_index` | Integer | Unique identifier for each variant |
| `generation` | Integer | Generation number (0 for wild-type/baseline) |
| `parent_variant_index` | Integer | Parent variant index (empty for generation 0) |
| `assembled_dna_sequence` | String | Complete DNA sequence (A/T/G/C) |
| `dna_yield` | Numeric | DNA yield measurement |
| `protein_yield` | Numeric | Protein yield measurement |

## File Format Examples

See the detailed [File Formats](step3-upload-data.md) section in this guide (coming soon).

## Next Steps

After upload completes, proceed to [Step 4: Process Sequences](step4-process-sequences.md).

---

**Related Topics:**

- [Step 2: Validate Plasmid](step2-validate-plasmid.md)
- [Step 4: Process Sequences](step4-process-sequences.md)
- [Workflow Overview](overview.md)
