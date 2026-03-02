# Common Issues

This page covers common issues you might encounter while using the Direct Evolution Monitoring Portal.

## Step 1: Fetch Wild-Type Issues

### UniProt accession not found

**Symptoms:**
- Error message: "UniProt accession not found"
- Failed to fetch protein data

**Solutions:**

1. Verify the accession number at [UniProt.org](https://www.uniprot.org/)
2. Check for typos or extra characters
3. Ensure the accession is still active (not obsolete)
4. Try searching by protein name if accession is uncertain

### Network or API errors

**Symptoms:**
- "Failed to fetch protein from UniProt"
- Timeout errors

**Solutions:**

1. Check your internet connection
2. Wait a few moments and retry
3. Verify UniProt is accessible: [https://www.uniprot.org/](https://www.uniprot.org/)
4. Contact support if issue persists

---

## Step 2: Validate Plasmid Issues

### Validation failed

**Symptoms:**
- Red "Error" badge
- "FAIL. No exact WT protein encoding found..."
- Low identity or coverage percentages

**Common Causes:**

1. **Wrong plasmid file** - Uploaded file doesn't match your wild-type protein
2. **Wrong UniProt accession** - Step 1 has incorrect reference protein
3. **Truncated sequence** - Plasmid missing coding regions
4. **Genetic code mismatch** - Non-standard codon usage

**Solutions:**

??? example "Check the error details"
    The error message shows:
    ```
    Best hit: identity=85.3%, coverage=92.1% on strand + frame 0
    ```
    
    - **Low identity (< 98%):** Amino acid sequence differs significantly
    - **Low coverage (< 98%):** Plasmid only partially encodes the protein
    
    **If identity is high but coverage is low:** Your plasmid may be missing regions (check for complete CDS)
    
    **If coverage is high but identity is low:** You may have the wrong protein or highly diverged sequence

??? example "Verify files match expected sequences"
    1. Open your plasmid FASTA in a text editor
    2. Translate it using a tool like [ExPASy Translate](https://web.expasy.org/translate/)
    3. Compare the translation to your UniProt sequence
    4. Verify they match (or identify where they differ)

??? example "Check for common formatting issues"
    - Ensure FASTA format is correct (header starts with `>`)
    - Remove any extra whitespace or special characters
    - Verify DNA alphabet (A, T, G, C)
    - Check file encoding (should be plain text)

### Invalid FASTA format

**Symptoms:**
- "Invalid FASTA format" error
- Failed to parse file

**Solutions:**

1. Ensure first line starts with `>`
2. Remove blank lines before header
3. Use only standard DNA nucleotides (A, T, G, C, N)
4. Check file is plain text (not Word doc or PDF)

Example valid FASTA:
```fasta
>MyPlasmid
ATGGCTAGCAAAGATGACGATGATAAAATG
GCTCAGGACATCGAAGAACTGGAAGCGATT
```

---

## Step 3: Upload Data Issues

### Missing required fields

**Symptoms:**
- Upload fails with "Missing required field: X"
- Parsing errors

**Solutions:**

1. Ensure all required columns are present:
   - `variant_index`
   - `generation`
   - `parent_variant_index`
   - `assembled_dna_sequence`
   - `dna_yield`
   - `protein_yield`

2. Check column names match exactly (case-sensitive)
3. Verify TSV/CSV delimiter (tab vs comma)

### Invalid data types

**Symptoms:**
- "Invalid value for field X"
- Type conversion errors

**Solutions:**

1. **Numeric fields** (`variant_index`, `generation`, `dna_yield`, `protein_yield`):
   - Must be numbers (integers or decimals)
   - No text or special characters
   
2. **DNA sequence field**:
   - Only A, T, G, C nucleotides
   - Remove spaces and special characters
   
3. **Parent index field**:
   - Integer for non-zero generations
   - Empty or null for generation 0

### Duplicate variant indices

**Symptoms:**
- Warning: "Duplicate variant_index detected"
- Upload succeeds but with warnings

**Solutions:**

1. Each variant should have a unique `variant_index`
2. Check your data for duplicate rows
3. Re-upload after removing duplicates

---

## Step 4: Sequence Processing Issues

### Processing failed

**Symptoms:**
- Red error message
- "Sequence processing failed"
- Step 4 shows error status

**Solutions:**

1. Check uploaded DNA sequences are valid:
   - Must be divisible by 3 (codons)
   - Must start with start codon (usually ATG)
   - Only A, T, G, C nucleotides

2. Verify wild-type protein is loaded (Step 1)
3. Try re-running Step 4
4. Check error logs if available

### Processing takes too long

**Symptoms:**
- Step 4 running for > 15 minutes
- No progress updates

**Solutions:**

1. Large datasets (> 10,000 variants) may take longer
2. Refresh the page to check current status
3. Processing runs in background - safe to close browser
4. Contact support if stuck for > 30 minutes

---

## Step 5: Analysis Issues

### No plots generated

**Symptoms:**
- Step 5 completes but no visualizations appear
- Missing PNG files

**Solutions:**

1. Ensure Step 4 completed successfully
2. Check that variants have activity scores
3. Try re-running Step 5
4. Verify sufficient data (need multiple variants)

### Plots show no data

**Symptoms:**
- Empty charts
- "No data available" messages

**Solutions:**

1. Verify Step 4 sequence processing completed
2. Check that variants were successfully uploaded in Step 3
3. Ensure activity scores were calculated
4. Try re-running the analysis pipeline

---

## General Issues

### Session expired

**Symptoms:**
- Redirected to login page
- "Session expired" message

**Solutions:**

1. Log back in
2. Navigate back to your experiment
3. Your data should be preserved
4. Continue from where you left off

### Browser compatibility

**Symptoms:**
- Layout issues
- Features not working

**Supported Browsers:**

- Chrome (recommended)
- Firefox
- Edge
- Safari

**Solutions:**

1. Update to latest browser version
2. Clear cache and cookies
3. Try a different browser
4. Disable browser extensions that may interfere

### Slow performance

**Solutions:**

1. Close unused browser tabs
2. Clear browser cache
3. Check internet connection speed
4. Try during off-peak hours

---

## Getting Additional Help

If your issue isn't covered here:

1. Check the [FAQs](faqs.md)
2. Review the relevant step guide:
   - [Step 1: Fetch Wild-Type](../workflow/step1-fetch-wildtype.md)
   - [Step 2: Validate Plasmid](../workflow/step2-validate-plasmid.md)
   - [Step 3: Upload Data](../workflow/step3-upload-data.md)
   - [Step 4: Process Sequences](../workflow/step4-process-sequences.md)
   - [Step 5: Run Analysis](../workflow/step5-run-analysis.md)
3. Check error messages for specific guidance
4. Contact the development team with:
   - Description of the issue
   - Steps to reproduce
   - Error messages (if any)
   - Browser and OS information

---

**Related Topics:**

- [FAQs](faqs.md)
- [Workflow Overview](../workflow/overview.md)
- [Home](../index.md)
