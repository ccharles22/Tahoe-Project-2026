# Step 4: Process Sequences

Process uploaded DNA sequences to generate protein sequences and identify mutations.

## Overview

This step:

- Translates DNA sequences to protein sequences
- Aligns proteins to wild-type reference
- Identifies mutations (substitutions, insertions, deletions)
- Calculates activity scores
- Stores analysis results

## Prerequisites

- ✅ **Completed Step 3** (Upload Data)

## How It Works

The sequence processing pipeline:

1. **Translation:** Convert DNA → protein using genetic code
2. **Alignment:** Align each variant to wild-type protein
3. **Mutation Calling:** Identify all amino acid changes
4. **Scoring:** Calculate activity scores based on yields
5. **Storage:** Save results to database

## Running Sequence Processing

1. Locate **Step 4** in the sidebar
2. Click **Run Sequence Processing**
3. Wait for background job to complete (may take several minutes)
4. Check status in the workflow panel

## What Gets Computed

- Protein sequences for all variants
- Mutation lists (e.g., `A123V`, `K45E`)
- Activity scores (normalized yields)
- Quality control metrics

## Next Steps

After processing completes, proceed to [Step 5: Run Analysis](step5-run-analysis.md).

---

**Related Topics:**

- [Step 3: Upload Data](step3-upload-data.md)
- [Step 5: Run Analysis](step5-run-analysis.md)
- [Workflow Overview](overview.md)
