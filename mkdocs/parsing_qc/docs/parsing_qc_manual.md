# Data Parsing & Quality Control Module

## Overview

The Data Parsing & QC module enables researchers to upload, parse, and validate directed evolution experimental data. It provides robust file handling, automatic field normalisation, and a two-tier quality control system that combines dataset-adaptive thresholds with absolute safety limits.

---

## Getting Started

### Accessing the Upload Page

Navigate to the upload page at:
```
http://your-server:5000/parsing/upload
```

### Uploading Data

1. **Select an Experiment**: Choose an existing experiment from the dropdown, or enter a new experiment ID
2. **Choose File**: Select your TSV, CSV, or JSON data file
3. **Submit**: Click "Upload" to process your data

![Upload Flow](images/upload_flow.png)

---

## Supported File Formats

### TSV/CSV Files

Tab-separated (`.tsv`) or comma-separated (`.csv`) text files. The parser automatically detects the delimiter.

**Expected Structure:**
```
Plasmid_Variant_Index	Parent_Plasmid_Variant	Directed_Evolution_Generation	Assembled_DNA_Sequence	DNA_Quantification_fg	Protein_Quantification_pg
1	-1	0	ATGCGATCG...	520.5	50.2
2	1	1	ATGCGATCG...	615.3	48.7
```

### JSON Files

JSON files containing an array of variant records or a nested object with a `records` or `variants` key.

**Supported Structures:**
```json
// Array of objects
[
  {"Plasmid_Variant_Index": 1, "Directed_Evolution_Generation": 0, ...},
  {"Plasmid_Variant_Index": 2, "Directed_Evolution_Generation": 1, ...}
]

// Nested with 'records' key
{
  "records": [
    {"Plasmid_Variant_Index": 1, ...}
  ]
}
```

---

## Required Fields

The following fields **must** be present in every record:

| Field Name | Description | Accepted Aliases |
|------------|-------------|------------------|
| `variant_index` | Unique identifier for the plasmid variant | `Plasmid_Variant_Index`, `variant_id`, `id` |
| `generation` | Directed evolution generation number (0 = wild-type) | `Directed_Evolution_Generation`, `gen`, `round` |
| `assembled_dna_sequence` | Full DNA sequence of the variant | `Assembled_DNA_Sequence`, `sequence`, `dna_sequence` |
| `dna_yield` | DNA quantification measurement | `DNA_Quantification_fg`, `dna_concentration` |
| `protein_yield` | Protein quantification measurement | `Protein_Quantification_pg`, `protein_concentration` |

### Optional Fields

| Field Name | Description | Accepted Aliases |
|------------|-------------|------------------|
| `parent_variant_index` | Parent variant ID (-1 or empty for generation 0) | `Parent_Plasmid_Variant`, `parent_id` |
| `control` | Whether this is a control sample | `Control`, `is_control` |

### Additional Metadata

Any columns not listed above are automatically captured and stored as **additional metadata**. This allows flexibility to include experiment-specific fields without modifying the parser.

---

## Quality Control System

The QC system uses a **two-tier threshold architecture** to identify potential data issues:

### Tier 1: Warnings (Adaptive Thresholds)

Warnings flag **statistical outliers** relative to the uploaded dataset. These use percentile-based thresholds computed dynamically.

**How it works:**
1. All yield values are collected from the uploaded dataset
2. The 1st percentile (P1) and 99th percentile (P99) are calculated
3. Values outside this range are flagged as warnings

**Configuration:**
```
Percentile Low:  P1  (1st percentile)
Percentile High: P99 (99th percentile)
Minimum Samples: 30  (required for stable percentile calculation)
```

**Example:**
If your dataset has DNA yields ranging from 400–1800 fg:
- Values below ~405 fg (P1) → Warning: "Unusually low DNA yield"
- Values above ~1750 fg (P99) → Warning: "Unusually high DNA yield"

### Tier 2: Errors (Critical Safety Limits)

Errors flag values that are **biologically or instrumentally impossible**. These are fixed limits based on assay specifications.

| Metric | Critical Minimum | Critical Maximum |
|--------|------------------|------------------|
| DNA Yield | 300 fg | 5000 fg |
| Protein Yield | 20 pg | 2000 pg |

Values outside these limits generate **errors** and the record is rejected.

### Why This Approach?

| Approach | Limitation |
|----------|------------|
| Fixed thresholds only | Don't account for batch-to-batch variation |
| Z-scores | Assume normal distribution (yield data often isn't) |
| **Percentiles + Critical Limits** | ✅ Non-parametric, robust to skewed distributions, catches impossible values |

### Visual Representation

```
        CRITICAL MIN        P1 WARNING       MEDIAN        P99 WARNING      CRITICAL MAX
             |                 |               |               |                |
    ═════════╪═════════════════╪═══════════════╪═══════════════╪════════════════╪═════════
       ERROR │    WARNING      │           OK  │    WARNING    │     ERROR
     (Reject)│   (Flag only)   │    (Accept)   │   (Flag only) │    (Reject)
```

---

## Validation Checks

### Per-Record Validation

Each record is individually checked for:

| Check | Type | Description |
|-------|------|-------------|
| Required fields | Error | All required fields must be present and non-empty |
| Data types | Error | `variant_index`, `generation` must be integers; yields must be numeric |
| DNA sequence characters | Error | Only A, T, G, C, N allowed |
| Sequence length | Warning | Flagged if unusually short (<100 bp) or long (>10,000 bp) |
| Yield ranges | Warning/Error | Based on adaptive + critical thresholds |
| Negative yields | Warning | Negative values flagged as potential measurement errors |

### Cross-Record Validation

The entire dataset is validated for consistency:

| Check | Type | Description |
|-------|------|-------------|
| Duplicate variant indices | Error | Each `variant_index` must be unique |
| Missing generation 0 | Warning | Dataset should include wild-type control (generation=0) |
| Generation continuity | Warning | Checks for gaps in generation numbers (e.g., 0,1,3 missing 2) |
| Orphaned parents | Warning | Parent variant IDs that don't exist in the dataset |

---

## Upload Results

After processing, you'll see one of two outcomes:

### Successful Upload

```
✅ Upload Successful

Your data has been parsed, validated, and stored in the database.

Summary:
- Total Records: 301
- Inserted: 285
- Updated: 16
- Warnings: 3

⚠️ Warnings (3)
- Row 45: Unusually high DNA yield (1923.5) - may indicate measurement error
- Row 112: protein yield (18.2) below typical range for this batch
- Missing generation 4. Found generations [0,1,2,3,5,6]. This may indicate incomplete data.
```

### Failed Upload

```
❌ Upload Failed

Validation failed with the following errors:

🚫 Errors (2)
- Row 23: Missing required fields: 'variant_index'. Expected columns: ...
- Duplicate variant indices found: [15, 42]. Each variant_index must be unique.
```

**Note:** If any record has a critical error, the **entire upload is rejected** to maintain data integrity.

---

## Configuring Thresholds

Thresholds can be customised in `parsing/config.py`:

### Validation Rules

```python
VALIDATION_RULES = {
    # Sequence length bounds
    'sequence_min_length': 100,
    'sequence_max_length': 10000,

    # Generic yield warnings (fallback)
    'yield_min_warning': 50.0,
    'yield_max_warning': 2000.0,

    # Per-metric overrides
    'dna_yield_max_warning': 2000.0,
    'protein_yield_min_warning': 40.0,
    'protein_yield_max_warning': 1000.0,

    # Allowed DNA characters
    'allowed_dna_chars': set('ATGCN'),
}
```

### QC Mode Settings

```python
# Enable percentile-based adaptive thresholds
QC_PERCENTILE_MODE = True
QC_PERCENTILE_LOW = 1.0    # Lower percentile (P1)
QC_PERCENTILE_HIGH = 99.0  # Upper percentile (P99)
QC_MIN_SAMPLES_FOR_PERCENTILES = 30

# Critical safety limits (always enforced)
DNA_YIELD_CRITICAL_MIN = 300.0
DNA_YIELD_CRITICAL_MAX = 5000.0
PROTEIN_YIELD_CRITICAL_MIN = 20.0
PROTEIN_YIELD_CRITICAL_MAX = 2000.0
```

---

## Error vs Warning Behaviour

| Condition | Behaviour | Upload Result |
|-----------|----------|---------------|
| **Error** | Record is invalid | ❌ Entire upload rejected |
| **Warning** | Record is unusual but valid | ⚠️ Upload succeeds, warning logged |

### What Generates Errors

- Missing required fields
- Invalid data types (non-numeric yields, non-integer variant_index)
- Invalid DNA characters in sequence
- Empty sequence
- Values outside critical safety limits
- Duplicate variant indices

### What Generates Warnings

- Negative yield values
- Extreme yields (outside P1/P99)
- Unusual sequence length
- Missing generation 0
- Gaps in generation numbers
- Orphaned parent references

---

## API Reference

### POST /parsing/upload/submit

Upload and process experimental data.

**Request Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | File | Yes | TSV, CSV, or JSON file |
| `experiment_id` | Integer | Yes | Target experiment ID |

**Response (Success):**
```json
{
  "success": true,
  "total_records": 301,
  "inserted_count": 285,
  "updated_count": 16,
  "warnings": ["Row 45: Unusually high DNA yield..."],
  "warnings_count": 3,
  "detected_fields": ["variant_index", "generation", "assembled_dna_sequence", "dna_yield", "protein_yield"]
}
```

**Response (Error):**
```json
{
  "success": false,
  "error_message": "Validation failed",
  "errors": ["Row 23: Missing required fields: 'variant_index'"]
}
```

### GET /parsing/health

Health check endpoint.

**Response:**
```json
{"status": "ok"}
```

---

## Troubleshooting

### Common Issues

| Problem | Cause | Solution |
|---------|-------|----------|
| "Missing required fields" | Column names don't match expected aliases | Check column headers match the accepted aliases |
| "variant_index must be an integer" | Non-numeric values in ID column | Ensure variant indices are whole numbers |
| "Invalid characters in sequence" | Sequence contains characters other than A,T,G,C,N | Clean sequence data before upload |
| "Duplicate variant indices" | Same ID used for multiple records | Assign unique IDs to each variant |
| "Connection timed out" | Database server unreachable | Check Tailscale/VPN connection |

### File Upload Limits

| Limit | Value |
|-------|-------|
| Maximum file size | 50 MB |
| Allowed extensions | `.tsv`, `.csv`, `.json` |

---

## Glossary

| Term | Definition |
|------|------------|
| **Variant** | A specific plasmid construct with a unique DNA sequence |
| **Generation** | The round of directed evolution (0 = wild-type ancestor) |
| **Parent Variant** | The variant from which a mutant was derived |
| **DNA Yield** | Quantification of DNA extracted (femtograms) |
| **Protein Yield** | Quantification of protein expressed (picograms) |
| **P1/P99** | 1st and 99th percentiles used for outlier detection |
| **Critical Limit** | Absolute boundary beyond which values are impossible |
