# Step 1: Fetch Wild-Type (UniProt)

The first step in the workflow is to retrieve the wild-type protein sequence from UniProt. This establishes the reference protein for your experiment and creates a new experiment workspace or updates an existing one.

## Overview

This step:

- Fetches protein sequence data from the UniProt database
- Retrieves protein annotations and features (domains, active sites, etc.)
- Creates a new experiment or associates the protein with an existing experiment
- Provides the reference sequence for downstream mutation analysis

## Prerequisites

Before starting, you'll need:

- A valid **UniProt accession number** for your wild-type protein (e.g., `O34996`, `P12345`)
- (Optional) An **experiment name** if creating a new experiment

!!! info "Finding UniProt Accessions"
    If you don't know your protein's UniProt accession:
    
    1. Visit [UniProt.org](https://www.uniprot.org/)
    2. Search by protein name, gene name, or organism
    3. Copy the accession number from the search results

## Step-by-Step Instructions

### 1. Navigate to the Workspace

From the portal homepage, click **Workspace** in the top navigation bar.

### 2. Locate Step A in the Sidebar

On the left sidebar, find the section labeled:

```
🔵 1 | Fetch WT (UniProt)
```

Click to expand the step if it's collapsed.

### 3. Enter UniProt Accession

In the **UniProt accession** field, enter your protein's accession number.

**Example:**
```
O34996
```

!!! tip "Accession Format"
    UniProt accessions are typically:
    
    - 6 characters for UniProtKB/Swiss-Prot entries (e.g., `P12345`)
    - 6 or 10 characters for UniProtKB/TrEMBL entries (e.g., `A0A0B4J2F2`)
    
    Enter the accession exactly as it appears in UniProt (case-insensitive).

### 4. (Optional) Enter Experiment Name

If you're creating a **new experiment**, you can provide a descriptive name in the **Experiment name** field.

**Example:**
```
BsuPol Round 1
```

!!! note "Existing Experiments"
    If you're working with an existing experiment (accessed via the Experiments tab), the experiment name field will be disabled and your existing experiment name will be preserved.

### 5. Click "Fetch WT"

Click the **Fetch WT** button to submit your request.

The button will show a loading spinner while the portal:

1. Connects to the UniProt API
2. Retrieves the protein sequence
3. Fetches annotations and features
4. Stores the data in the database
5. Creates or updates your experiment

### 6. Verify Success

Upon successful completion, you'll see:

- A green **"Complete"** badge next to the step title
- A summary showing: `Complete: [UniProt ID] | [sequence length] aa`
- A confirmation message (if displayed)

The **WT Protein Summary** panel in the main workspace will populate with:

- Protein name and organism
- Sequence length and plasmid template information (if available)
- UniProt annotations (domains, active sites, binding sites, etc.)

## What Data is Retrieved?

The portal fetches the following information from UniProt:

| Data Type | Description | Usage |
|-----------|-------------|-------|
| **Protein Sequence** | Full amino acid sequence | Reference for mutation calling |
| **Protein Name** | Official protein name | Display and documentation |
| **Organism** | Source organism | Metadata |
| **Features** | Domains, active sites, binding regions, modifications | Enhanced visualization and analysis |
| **Gene Name** | Associated gene name(s) | Metadata |
| **Cross-References** | Links to other databases | Additional context |

## Common Issues

### "UniProt accession not found"

**Cause:** The accession number doesn't exist in UniProt or contains a typo.

**Solution:**

1. Double-check the accession number in [UniProt.org](https://www.uniprot.org/)
2. Ensure there are no extra spaces or characters
3. Try searching for your protein by name if the accession is uncertain

### "Failed to fetch protein from UniProt"

**Cause:** Temporary network issue or UniProt API unavailable.

**Solution:**

1. Wait a few moments and try again
2. Check your internet connection
3. If the problem persists, contact support

### Re-fetching Wild-Type Data

If you need to update or change the wild-type protein:

1. Enter a new UniProt accession
2. Click **Re-fetch WT** (button text changes if WT already exists)
3. The system will update the wild-type protein for this experiment

!!! warning "Impact of Re-fetching"
    Re-fetching the wild-type protein will:
    
    - Update the reference sequence
    - May affect mutation calling if sequences differ
    - Preserve uploaded variant data in Steps 3-5
    
    Consider the impact before re-fetching if you've already completed downstream steps.

## Example: Fetching a Bacterial Polymerase

Let's walk through a complete example:

**Scenario:** You're analyzing directed evolution of a DNA polymerase from *Bacillus subtilis*.

1. Search UniProt for "DNA polymerase III Bacillus subtilis"
2. Find the entry with accession **O34996**
3. In Step A, enter `O34996` in the UniProt accession field
4. Enter experiment name: `BsuPol Round 1`
5. Click **Fetch WT**
6. Verify the summary shows:
   - **Complete: O34996 | 456 aa** (or similar)
   - Protein name: *DNA polymerase III subunit alpha*
   - Organism: *Bacillus subtilis*

## Next Steps

Once Step 1 is complete:

- **Step 2** (Validate Plasmid) will become available
- You can optionally validate your plasmid FASTA file
- Or skip directly to **Step 3** (Upload Data) to upload variant data

!!! success "Step Complete!"
    With your wild-type protein loaded, you're ready to proceed to [Step 2: Validate Plasmid](step2-validate-plasmid.md) or skip ahead to [Step 3: Upload Data](step3-upload-data.md).

---

**Related Topics:**

- [Step 2: Validate Plasmid](step2-validate-plasmid.md)
- [Step 3: Upload Data](step3-upload-data.md)
- [Workflow Overview](overview.md)
- [Troubleshooting](../troubleshooting/common-issues.md)
