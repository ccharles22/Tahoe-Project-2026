# Edge Cases Test Documentation

This document describes the edge case tests implemented in `test_edge_cases.py` for the data parsing and QC pipeline.

## Overview

The edge case tests validate that the system handles problematic data gracefully, provides actionable error messages, and maintains data integrity.

## Test Categories

### 1. Empty Files (`TestEmptyFiles`)

**Scenarios:**
- Completely empty TSV file (0 bytes)
- Completely empty JSON file (0 bytes)
- JSON with empty array `[]`

**Expected Behavior:**
- Parser returns `False`
- Clear error message explaining the file is empty
- Suggestion to provide file with headers and data

**Common Real-World Cause:**
- File transfer interrupted
- User selected wrong file
- Automated system generated empty output

---

### 2. Headers Only (`TestHeadersOnly`)

**Scenarios:**
- TSV with header row but no data rows

**Expected Behavior:**
- Parser returns `False`
- Error message indicating no data rows found
- Suggestion to add data rows after headers

**Common Real-World Cause:**
- Incomplete export from LIMS
- Template file uploaded by mistake
- Filter operation removed all data

---

### 3. Single Valid Record (`TestSingleRecord`)

**Scenarios:**
- Minimal valid file with one record

**Expected Behavior:**
- Parser returns `True`
- No errors
- Record successfully parsed and validated

**Purpose:**
- Establishes baseline for what constitutes valid data
- Tests minimum viable input

---

### 4. Mixed Valid/Invalid Records (`TestMixedRecords`)

**Scenarios:**
- File with mix of valid and invalid records:
  - Valid record (row 2)
  - Invalid generation type (row 3)
  - Invalid dna_yield "N/A" (row 4)
  - Valid record (row 5)
  - Invalid sequence with numbers (row 6)

**Expected Behavior:**
- Parser successfully reads all rows
- QC validation identifies specific errors per row
- Error messages include row numbers
- Error messages provide actionable guidance

**HTTP Response:** 400 (validation failed)

---

### 5. Large Files (`TestLargeFiles`)

**Scenarios:**
- File with 1000+ valid records across multiple generations

**Expected Behavior:**
- Parser handles large files without memory issues
- All records parsed correctly
- QC validation completes in reasonable time
- No false positives on large datasets

**Performance Notes:**
- Current implementation loads entire file into memory
- For production with very large files, consider streaming

---

### 6. Duplicate Variant Indices (`TestDuplicateIndices`)

**Scenarios:**
- Multiple records sharing the same `variant_index`

**Expected Behavior:**
- **ERROR** (not warning) - duplicates violate unique constraint
- Error message lists all duplicate indices
- Error message shows which rows are affected
- Guidance to assign unique IDs

**Database Impact:**
- Would cause constraint violation on insert
- Caught during QC before database operation

---

### 7. Missing Generation 0 (`TestMissingGeneration`)

**Scenarios:**
- File with generations 1, 2, 3... but no generation 0

**Expected Behavior:**
- **WARNING** (not error) - data may still be valid
- Warning suggests adding wild-type control records
- Explains purpose of generation 0 (baseline)

**Why Warning Not Error:**
- Some experiments may legitimately start at generation 1
- User should decide whether to add WT controls

---

### 8. Orphaned Parent Variants (`TestOrphanedParents`)

**Scenarios:**
- Records reference `parent_variant_index` values that don't exist in the dataset

**Expected Behavior:**
- **WARNING** (not error)
- Lists specific orphaned references
- Suggests including parent variants or correcting references

**Why Warning Not Error:**
- Parent may exist in different batch/experiment
- Cross-experiment lineage may be intentional

---

### 9. Invalid Sequences (`TestInvalidSequences`)

**Scenarios:**
- Sequences with numbers (123)
- Sequences with lowercase letters
- Sequences with spaces
- Sequences with special characters (@#$)
- Very short sequences (< 100 bp)

**Expected Behavior:**
- Invalid characters: **ERROR**
- Short sequences: **WARNING**
- Error messages list invalid characters found
- Error messages show valid character set
- Suggestions to ensure uppercase nucleotide codes

**Valid Characters:** A, T, G, C, N

---

### 10. Type Mismatches (`TestTypeMismatches`)

**Scenarios:**
- `variant_index`: "abc" (should be integer)
- `generation`: "xyz" (should be integer)
- `parent_variant_index`: "abc" (should be integer or NULL)
- `dna_yield`: "N/A" (should be numeric)
- `protein_yield`: "null" (should be numeric)

**Expected Behavior:**
- Clear error per field
- Shows the invalid value received
- Provides example of valid value
- Suggests alternatives (e.g., "use 0 if unknown")

---

### 11. Empty Required Fields (`TestEmptyRequiredFields`)

**Scenarios:**
- Empty `variant_index`
- Empty `generation`
- Empty `dna_yield`
- Empty `protein_yield`
- Empty `assembled_dna_sequence`

**Expected Behavior:**
- **ERROR** - required fields cannot be empty
- Lists which fields are missing
- Shows expected column names and alternatives

---

### 12. Malformed JSON (`TestMalformedJSON`)

**Scenarios:**
- Truncated JSON
- Missing closing brackets
- Invalid syntax

**Expected Behavior:**
- Parser returns `False`
- Error includes line and column number
- Suggests using JSON validator tool

---

### 13. Row Number Reporting (`TestRowNumberReporting`)

**Scenarios:**
- Verify all per-record errors include row numbers
- Verify TSV row numbers start at 2 (row 1 = headers)
- Verify JSON row numbers start at 1

**Expected Behavior:**
- All errors formatted as "Row X: description"
- Users can find exact location of problems

---

## Error Message Guidelines

All error messages follow these principles:

1. **Include row number** - "Row 5: ..."
2. **State the problem** - "dna_yield must be numeric"
3. **Show the invalid value** - "got 'N/A'"
4. **Provide guidance** - "Please provide a valid number (e.g., 100.5)"
5. **Suggest alternatives** - "Use 0 if unknown"

### Example Error Messages

**Before (unhelpful):**
```
Row 5: dna_yield must be numeric, got 'N/A'
```

**After (actionable):**
```
Row 5: dna_yield must be numeric, got 'N/A'. Please provide a valid number (e.g., 100.5, 85.2). Use 0 if unknown.
```

---

## Running Edge Case Tests

```bash
# Run all edge case tests
pytest tests/test_edge_cases.py -v

# Run specific test class
pytest tests/test_edge_cases.py::TestEmptyFiles -v

# Run with output for debugging
pytest tests/test_edge_cases.py -v -s
```

---

## Creating Additional Test Files

To add new edge case tests:

1. Create a fixture function that generates the test file:
```python
@pytest.fixture
def my_edge_case_file():
    content = "..."  # Your test data
    temp = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.tsv')
    temp.write(content)
    temp.close()
    yield temp.name
    os.unlink(temp.name)  # Cleanup
```

2. Create test function(s) using the fixture:
```python
def test_my_edge_case(my_edge_case_file):
    parser = TSVParser(my_edge_case_file)
    result = parser.parse()
    # Assertions...
```

---

## HTTP Status Codes

| Scenario | Status Code | Response Key |
|----------|-------------|--------------|
| Empty file | 400 | `error` |
| Headers only | 400 | `error` |
| Validation errors | 400 | `error`, `errors` |
| Warnings only | 200 | `success`, `warnings` |
| Database error | 500 | `error`, `details` |
| Success | 200 | `success`, `inserted_count` |

---

## Database State After Errors

All error scenarios should result in:
- No partial inserts
- Database transaction rolled back
- Clean state maintained

This is verified by the `test_upload_db_rollback_on_error` test in `test_upload.py`.
