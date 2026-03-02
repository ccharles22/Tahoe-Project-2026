# Frequently Asked Questions (FAQs)

## General Questions

### What is directed evolution?

Directed evolution is a method used in protein engineering that mimics the process of natural selection to evolve proteins or nucleic acids toward a user-defined goal. The process involves:

1. Creating a library of variants
2. Screening for desired properties
3. Selecting the best performers
4. Using them as templates for the next generation
5. Repeating the cycle

### What does this portal do?

The Direct Evolution Monitoring Portal helps researchers:

- Organize and validate experimental data
- Process DNA sequences automatically
- Identify mutations across generations
- Visualize evolutionary trajectories
- Analyze activity scores and lineages
- Identify high-performing variants

### Do I need to install anything?

No! The portal is entirely web-based. You only need:

- A modern web browser (Chrome, Firefox, Edge, or Safari)
- Internet connection
- Your experiment data files

### Is my data secure?

Yes. The portal uses:

- Secure authentication
- Session-based access control
- Database isolation per user
- No data sharing between users

## Account & Access

### Do I need an account?

You can use the portal as a guest, but creating an account is recommended for:

- Long-term access to your experiments
- Saving work across sessions
- Managing multiple experiments

### Can I work on multiple experiments?

Yes! You can:

- Create multiple experiments
- Switch between them using the Experiments tab
- Each experiment maintains its own workspace and data

### What happens to guest sessions?

Guest sessions are temporary:

- Data is preserved during your browser session
- May be cleared after logout
- For permanent storage, create an account

## Data & File Format

### What file formats are supported?

**Step 2 (Plasmid):**
- FASTA format (`.fa`, `.fasta`, `.txt`)

**Step 3 (Variant Data):**
- TSV (tab-separated values)
- CSV (comma-separated values)
- JSON

### How large can my files be?

**Typical limits:**
- Plasmid FASTA: < 50 MB (more than sufficient for most plasmids)
- Variant data: < 100 MB or ~50,000 variants

For larger datasets, contact support.

### What if I have data in a different format?

Convert your data to TSV, CSV, or JSON with the required columns:

- `variant_index`
- `generation`
- `parent_variant_index`
- `assembled_dna_sequence`
- `dna_yield`
- `protein_yield`

Most spreadsheet software (Excel, Google Sheets) can export to TSV or CSV.

### Can I edit data after uploading?

Not directly in the portal. To make changes:

1. Edit your source file
2. Re-upload via Step 3
3. Re-run Steps 4 and 5

## Workflow Questions

### Can I skip steps?

- **Step 1:** Required (must fetch wild-type)
- **Step 2:** Optional (can skip plasmid validation)
- **Step 3:** Required (must upload data)
- **Step 4:** Required (must process sequences)
- **Step 5:** Recommended (generates visualizations)

### Can I go back and change earlier steps?

Yes! You can:

- Re-fetch wild-type (Step 1) - may affect downstream results
- Re-validate plasmid (Step 2) - safe to change
- Re-upload data (Step 3) - replaces previous data
- Re-run sequence processing (Step 4) - if data changed
- Re-run analysis (Step 5) - regenerates plots

### How long does processing take?

Approximate times:

| Step | Time |
|------|------|
| Step 1 | 5-10 seconds |
| Step 2 | 5-15 seconds |
| Step 3 | 10-60 seconds |
| Step 4 | 1-10 minutes (depends on variant count) |
| Step 5 | 30-120 seconds |

### What if processing gets stuck?

1. Refresh the page (processing continues in background)
2. Check status in the stepper bar
3. Wait up to 30 minutes for large datasets
4. Contact support if no progress after 30 minutes

## Protein & Sequence Questions

### What is a UniProt accession?

A UniProt accession is a unique identifier for proteins in the Universal Protein Resource database. Examples:

- `P12345` (6 characters)
- `O34996` (6 characters)
- `A0A0B4J2F2` (10 characters)

Find accessions at [UniProt.org](https://www.uniprot.org/)

### Why do I need a plasmid sequence?

Plasmid validation (Step 2) is **optional** but helps:

- Verify your template encodes the expected protein
- Catch sequence errors early
- Validate circular plasmid topology
- Confirm reading frame and strand

You can skip this step if you don't have a plasmid sequence.

### What genetic code is used?

By default, the portal uses the **standard genetic code (table 1)**.

For organisms with alternative genetic codes (mitochondria, some bacteria), contact support.

### How are mutations called?

The portal:

1. Translates DNA to protein
2. Aligns each variant to wild-type
3. Identifies amino acid differences
4. Reports mutations in standard notation (e.g., `A123V` = Alanine at position 123 → Valine)

### What is an activity score?

Activity scores are calculated from your measurements (typically protein yield or activity):

- Normalized to wild-type or generation 0 baseline
- Higher scores indicate better performance
- Used for ranking and visualization

## Visualization Questions

### What plots are generated?

**Standard visualizations:**

1. **Activity Distribution** - Histogram of activity scores
2. **Lineage Tree** - Evolutionary ancestry graph
3. **Top 10 Variants** - Best performers ranked
4. **Protein Similarity Network** - Sequence similarity graph

**Bonus visualizations (optional):**

5. Activity landscape (3D PCA)
6. Mutation fingerprints (per-variant heatmaps)
7. Domain enrichment heatmaps
8. Mutation frequency plots

### Can I download the plots?

Yes! All plots are available as:

- PNG images (for presentations)
- CSV files (for further analysis)
- Interactive HTML (for exploration)

Right-click on any image to save it.

### Can I customize the visualizations?

The portal generates standard visualizations automatically. For custom analysis:

1. Download the CSV files
2. Use your own analysis tools (R, Python, Excel, etc.)
3. Raw data is available in the database

## Technical Questions

### What technology does the portal use?

**Backend:**
- Python / Flask
- PostgreSQL database
- BioPython for sequence analysis

**Frontend:**
- HTML, CSS, JavaScript
- Bootstrap for styling
- Plotly/Matplotlib for visualizations

### Can I access the database directly?

Not through the web interface. To export data:

1. Download CSV files from Step 5
2. Contact support for bulk exports
3. API access may be available (contact support)

### Is there an API?

API documentation is under development. Contact the development team for current API capabilities.

### Can I run this on my own server?

The portal is designed for web deployment. For local installation:

1. See the `DEPLOYING.md` file in the repository
2. Requires Python, PostgreSQL, and Redis
3. Contact support for deployment assistance

## Error Messages

### "UniProt accession not found"

The accession doesn't exist in UniProt. Check spelling and verify at [UniProt.org](https://www.uniprot.org/).

### "Validation FAILED"

Your plasmid doesn't encode the wild-type protein with ≥98% identity and coverage. See [Common Issues - Validation Failed](common-issues.md#validation-failed).

### "Missing required field"

Your upload file is missing a required column. Ensure all required fields are present:

- `variant_index`, `generation`, `parent_variant_index`, `assembled_dna_sequence`, `dna_yield`, `protein_yield`

### "Sequence processing failed"

DNA sequences may be invalid or incompatible. Check:

- Sequences contain only A, T, G, C
- Sequences are multiples of 3 (codons)
- No empty or null sequences

See [Common Issues](common-issues.md) for detailed troubleshooting.

## Still Have Questions?

- Review the [Workflow Overview](../workflow/overview.md)
- Check [Common Issues](common-issues.md)
- Consult individual step guides:
  - [Step 1: Fetch Wild-Type](../workflow/step1-fetch-wildtype.md)
  - [Step 2: Validate Plasmid](../workflow/step2-validate-plasmid.md)
  - [Step 3: Upload Data](../workflow/step3-upload-data.md)
  - [Step 4: Process Sequences](../workflow/step4-process-sequences.md)
  - [Step 5: Run Analysis](../workflow/step5-run-analysis.md)
- Contact the development team

---

**Related Topics:**

- [Home](../index.md)
- [Workflow Overview](../workflow/overview.md)
- [Common Issues](common-issues.md)
