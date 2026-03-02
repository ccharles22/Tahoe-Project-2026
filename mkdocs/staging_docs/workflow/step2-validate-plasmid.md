# Step 2: Validate Plasmid

Step 2 validates that your plasmid DNA sequence correctly encodes the wild-type protein fetched in Step 1. This optional but recommended step ensures your reference sequence matches your experimental template.

## Overview

This step:

- Accepts a plasmid FASTA file containing the DNA template sequence
- Validates that the plasmid encodes the wild-type protein
- Uses 6-frame translation (forward and reverse strands, all reading frames)
- Checks for exact or approximate matches with configurable thresholds
- Supports circular plasmid DNA sequences

!!! info "Optional Step"
    Step 2 is **optional**. You can skip directly to Step 3 (Upload Data) if you don't have a plasmid sequence or don't need validation. However, validating your plasmid helps ensure data quality and catches potential issues early.

## Prerequisites

Before starting, you must have:

- ✅ **Completed Step 1** (Fetch Wild-Type)
- 📄 A **FASTA file** containing your plasmid DNA sequence

!!! warning "Step Locked"
    This step is locked until you complete Step 1. Complete [Step 1: Fetch Wild-Type](step1-fetch-wildtype.md) first.

## How Validation Works

The validation process:

1. **Reads your plasmid FASTA file** (linear or circular DNA sequence)
2. **Duplicates the sequence** to handle circular plasmids (creates `DNA + DNA` concatenation)
3. **Generates reverse complement** to check both strands
4. **Translates all 6 reading frames:**
   - Forward strand: frames 0, 1, 2
   - Reverse strand: frames 0, 1, 2
5. **Searches for exact match** first
6. **Falls back to local alignment** if exact match not found
7. **Reports identity and coverage** percentages

### Validation Criteria

| Criterion | Threshold | Description |
|-----------|-----------|-------------|
| **Exact Match** | 100% | Wild-type protein found as exact substring in translated frame |
| **Identity** | ≥ 98% | Percentage of identical amino acids in aligned region |
| **Coverage** | ≥ 98% | Percentage of wild-type protein covered by alignment |

!!! success "Pass Conditions"
    Validation **passes** if:
    
    - An exact match is found in any of the 6 reading frames, OR
    - Local alignment achieves ≥98% identity AND ≥98% coverage

## Step-by-Step Instructions

### 1. Prepare Your Plasmid FASTA File

Your FASTA file should contain a single DNA sequence in standard FASTA format:

```fasta
>MyPlasmid_pET28a_BsuPol
ATGGCTAGCAAAGATGACGATGATAAAATGGCTCAGGACATCGAAGAACTG
GAAGCGATTCGCGACGTGATTGAAGAACTGGCGCGTGACATGGAAGAACTG
GCGCGTGACATGGAACTGAAAGATGACGTGATTAAAGAACTGGAAGCGATT
...
```

**Format requirements:**

- Standard FASTA format with `>` header line
- DNA sequence (A, T, G, C nucleotides)
- Can be on single line or multiple lines
- Case-insensitive (will be converted to uppercase)

!!! tip "Circular Plasmids"
    The validator automatically handles circular plasmids. If your wild-type protein spans the origin of replication (wraps around), the validator will detect it by duplicating your sequence.

### 2. Locate Step B in the Sidebar

On the left sidebar, find the section labeled:

```
🟡 2 | Validate Plasmid
```

Click to expand the step if it's collapsed.

### 3. Upload Plasmid FASTA

1. Click **Choose File** in the "Plasmid FASTA" field
2. Select your FASTA file from your computer
3. Click the **Validate** button

The button will show a loading spinner while the portal:

1. Reads and parses your FASTA file
2. Validates the sequence format
3. Performs 6-frame translation
4. Searches for the wild-type protein
5. Calculates identity and coverage metrics

### 4. Interpret Results

The validation will complete with one of three outcomes:

#### ✅ **PASS: Exact Match**

```
PASS: WT protein is exactly encoded in the uploaded plasmid.
```

- Wild-type protein found as exact substring
- 100% identity, 100% coverage
- Green "Complete" badge displayed

#### ✅ **PASS: Approximate Match**

```
PASS: Approximate match satisfies thresholds (98.5% identity, 99.2% coverage).
```

- Wild-type protein aligned with high similarity
- Meets or exceeds thresholds (≥98% identity and coverage)
- Green "Complete" badge displayed

#### ❌ **FAIL: Insufficient Match**

```
FAIL. No exact WT protein encoding found across six translated frames.
Best hit: identity=85.3%, coverage=92.1% on strand + frame 0.
```

- No exact match found
- Best alignment below thresholds
- Red "Error" badge displayed
- Shows best match details for debugging

## Validation Output Details

When validation completes, you'll see:

- **Badge status** (Complete or Error)
- **Success/failure message** with details
- **Identity percentage** (if approximate match)
- **Coverage percentage** (if approximate match)
- **Strand and frame** information (where protein was found)

The validated plasmid sequence is stored in your experiment metadata and may be used for:

- Back-translation from protein to DNA
- Codon usage analysis
- Future validation checks

## Common Issues

### "Validation FAILED"

**Possible Causes:**

1. **Wrong plasmid file** - Uploaded plasmid doesn't encode the wild-type protein
2. **Wrong UniProt accession** - Step 1 fetched the wrong protein
3. **Truncated sequence** - Plasmid is missing portions of the coding sequence
4. **Different genetic code** - Organism uses non-standard genetic code

**Solutions:**

??? tip "Verify UniProt Accession"
    1. Check that the UniProt accession in Step 1 is correct
    2. Re-fetch the wild-type protein if needed
    3. Ensure the protein matches your experimental construct

??? tip "Check Plasmid File"
    1. Open your FASTA file in a text editor
    2. Verify it contains DNA (not protein) sequence
    3. Check for completeness - ensure the full coding sequence is present
    4. Look for any truncations or missing regions

??? tip "Inspect the Best Match"
    The error message shows the best match details:
    
    - **Identity < 98%**: Significant differences in amino acid sequence
    - **Coverage < 98%**: Wild-type protein only partially covered
    
    If identity is high (>95%) but coverage is low, your plasmid may be missing regions.
    
    If coverage is high but identity is low, you may have the wrong protein or a highly mutated template.

??? tip "Genetic Code Tables"
    The validator uses the standard genetic code (table 1) by default. If your organism uses a different genetic code:
    
    - Mitochondrial genomes may require code 2, 3, or 5
    - Some bacterial genera use code 4 or 11
    
    Contact support if you need a different genetic code table.

### "Invalid FASTA format"

**Cause:** The uploaded file doesn't follow FASTA format.

**Solution:**

1. Ensure first line starts with `>`
2. Remove any blank lines before the header
3. Ensure DNA sequence contains only A, T, G, C (N allowed for ambiguous bases)
4. Check file encoding (should be plain text, UTF-8)

### "Plasmid sequence too short"

**Cause:** The DNA sequence is shorter than expected for encoding the wild-type protein.

**Solution:**

1. Wild-type protein length × 3 = minimum expected DNA length
2. Check that the FASTA file contains the complete sequence
3. Verify no truncation occurred during file creation

### Re-uploading After Failure

If validation fails, you can:

1. Correct the issue (wrong file, wrong protein, etc.)
2. Click **Choose File** again to upload a corrected FASTA
3. Click **Validate** to re-run the validation

## Advanced: Understanding 6-Frame Translation

The validator checks **all possible translations** of your DNA:

<div class="mermaid">
graph TD
    A[Plasmid DNA] --> B[Duplicate for Circular]
    B --> C[Forward Strand]
    B --> D[Reverse Complement]
    C --> E[Frame 0]
    C --> F[Frame +1]
    C --> G[Frame +2]
    D --> H[Frame 0]
    D --> I[Frame +1]
    D --> J[Frame +2]
    E --> K{Match?}
    F --> K
    G --> K
    H --> K
    I --> K
    J --> K
    K -->|Yes| L[PASS]
    K -->|No| M[Try Local Alignment]
    M --> N{Identity & Coverage ≥98%?}
    N -->|Yes| L
    N -->|No| O[FAIL]
</div>

This comprehensive approach ensures the wild-type protein is found regardless of:

- Which strand it's encoded on (forward or reverse)
- Which reading frame is used
- Whether it spans the circular origin

## Example: Validating a pET28a Plasmid

**Scenario:** You've cloned your *B. subtilis* DNA polymerase gene into a pET28a vector.

1. Export the complete plasmid sequence from your cloning software
2. Save as `pET28a_BsuPol.fasta`:

```fasta
>pET28a_BsuPol_construct
ATGGGCAGCAGCCATCATCATCATCATCACAGCAGCGGCCTGGTGCCGCGCGGCAGC
CATGGCTAGCAAAGATGACGATGATAAAATGGCTCAGGACATCGAAGAACTGGAAGCG
ATTCGCGACGTGATTGAAGAACTGGCGCGTGACATGGAAGAACTGGCGCGTGACATGG
AACTGAAAGATGACGTGATTAAAGAACTGGAAGCGATT...
```

3. Upload via Step 2
4. Expected result:

```
✓ PASS: WT protein is exactly encoded in the uploaded plasmid.
Complete: O34996 | Strand: + | Frame: 1
```

## Next Steps

After completing or skipping Step 2:

- Proceed to **[Step 3: Upload Data](step3-upload-data.md)** to upload variant data
- Step 3 is accessible after Step 1 (Step 2 is optional)

!!! success "Step Complete!"
    Your plasmid is validated! Continue to [Step 3: Upload Data](step3-upload-data.md) to upload your variant measurements.

!!! info "Skipping This Step"
    If you don't have a plasmid sequence or prefer to skip validation:
    
    - Click directly on **Step 3** in the sidebar
    - Upload your variant data
    - The portal will use the UniProt protein sequence as the reference

---

**Related Topics:**

- [Step 1: Fetch Wild-Type](step1-fetch-wildtype.md)
- [Step 3: Upload Data](step3-upload-data.md)
- [Workflow Overview](overview.md)
- [Troubleshooting](../troubleshooting/common-issues.md)
