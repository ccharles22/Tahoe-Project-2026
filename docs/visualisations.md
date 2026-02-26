# Visualisations — Sequence Processing User Guide

This guide walks you through every stage of the Tahoe sequence processing pipeline, from raw plasmid DNA to mutation reports. Each section includes **definitions**, **visual diagrams**, and **code examples** you can run directly in the portal.

---

## Table of Contents

1. [Key Concepts & Definitions](#key-concepts-definitions)
2. [Pipeline Overview](#pipeline-overview)
3. [Step 1 — Wild-Type Gene Mapping](#step-1-wild-type-gene-mapping)
4. [Step 2 — Variant CDS Extraction](#step-2-variant-cds-extraction)
5. [Step 3 — Translation & Quality Control](#step-3-translation-quality-control)
6. [Step 4 — Mutation Calling](#step-4-mutation-calling)
7. [Step 5 — Interpreting Results](#step-5-interpreting-results)
8. [Visualisation Code Examples](#visualisation-code-examples)
9. [Troubleshooting & QC Flags](#troubleshooting-qc-flags)

---

## Key Concepts & Definitions

Before using the pipeline, familiarise yourself with these terms:

### Molecular Biology

| Term | Definition |
|------|-----------|
| **Plasmid** | A small, circular DNA molecule found in bacteria. In directed evolution, the gene of interest is cloned into a plasmid for expression and mutagenesis. |
| **CDS (Coding DNA Sequence)** | The portion of the plasmid that encodes the protein. Starts with a start codon (ATG) and ends with a stop codon (TAA/TAG/TGA). |
| **Codon** | A sequence of 3 DNA nucleotides (e.g., ATG, GCT) that encodes a single amino acid. |
| **Reading Frame** | One of 3 possible ways to divide a DNA sequence into codons. Frame 0 starts at position 0, frame 1 at position 1, frame 2 at position 2. |
| **Strand** | DNA is double-stranded. The **PLUS** (sense) strand reads 5′→3′; the **MINUS** (antisense) strand is the reverse complement. The gene can be on either strand. |
| **Wild-Type (WT)** | The original, unmodified reference sequence — the starting point before mutations are introduced. |
| **Variant** | A modified version of the plasmid produced by mutagenesis. Each variant may contain zero or more mutations relative to the WT. |

### Pipeline-Specific

| Term | Definition |
|------|-----------|
| **WTMapping** | The result of locating the WT gene in the plasmid. Contains the strand, reading frame, CDS start/end coordinates, and the extracted WT CDS and protein sequences. |
| **VariantSeqResult** | The result of extracting and translating a single variant's CDS. Contains the DNA sequence, translated protein, and quality control flags. |
| **QCFlags** | A set of boolean flags indicating quality issues: frameshifts, ambiguous bases, or premature stop codons. |
| **MutationRecord** | A single mutation detected between the WT and a variant, classified as SYNONYMOUS, NONSYNONYMOUS, NONSENSE, FRAMESHIFT, INSERTION, DELETION, or AMBIGUOUS. |
| **MutationCounts** | Aggregated mutation statistics: counts of synonymous, nonsynonymous, and total mutations for a variant. |

### Mutation Types

| Type | Symbol | Definition | Effect |
|------|--------|-----------|--------|
| **Synonymous** | SYN | Codon changes but amino acid stays the same (e.g., GCT→GCC both encode Alanine) | Silent — no protein change |
| **Nonsynonymous** | NONSYN | Codon changes AND amino acid changes (e.g., GCT→GAT: Ala→Asp) | Alters protein sequence |
| **Nonsense** | STOP | Mutation introduces a premature stop codon (e.g., TGG→TGA: Trp→Stop) | Truncates protein |
| **Frameshift** | FS | Insertion or deletion of bases not divisible by 3, shifting the reading frame | Scrambles downstream protein |
| **Insertion** | INS | One or more codons added to the variant that are absent in the WT | Lengthens protein |
| **Deletion** | DEL | One or more codons present in the WT are absent in the variant | Shortens protein |
| **Ambiguous** | AMB | Variant codon contains non-ACGT bases (N, R, Y, etc.) — cannot classify | Unknown effect |

---

## Pipeline Overview

The pipeline processes each experiment in **five stages**. Every variant is compared against the same wild-type reference.

```
┌───────────────────────────────────────────────────────────────────┐
│                        INPUT                                      │
│  • WT protein sequence (from UniProt)                             │
│  • WT plasmid DNA (circular, ~3–10 kb)                            │
│  • Variant plasmid DNAs (one per variant, assembled reads)        │
└─────────────────────────────┬─────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1 — Wild-Type Gene Mapping                                │
│  Find the CDS in the plasmid using 6-frame protein alignment    │
│  Output: WTMapping (strand, frame, coordinates, CDS, protein)   │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2 — Variant CDS Extraction (per variant)                  │
│  Use WT coordinates to extract the same region from each variant │
│  Handles circular plasmids, MINUS strand, wrap-around genes      │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3 — Translation & QC (per variant)                        │
│  Translate CDS → protein, check for frameshifts, stops, Ns      │
│  Output: VariantSeqResult with QCFlags                           │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 4 — Mutation Calling (per variant)                        │
│  Compare variant CDS against WT CDS                              │
│  Strategy: codon-by-codon (same length) or alignment (indels)   │
│  Output: List[MutationRecord] + MutationCounts                   │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 5 — Results & Database Persistence                        │
│  Store proteins, mutations, metrics → PostgreSQL                 │
│  Experiment status: ANALYSED / ANALYSED_WITH_ERRORS / FAILED    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Step 1 — Wild-Type Gene Mapping

### What Happens

The pipeline must find where your gene of interest sits within the circular plasmid. Since plasmids also contain backbone elements (origin of replication, antibiotic resistance markers, etc.), we need to pinpoint the exact CDS coordinates.

### How It Works — 6-Frame Translation Search

A circular plasmid can encode proteins on **either strand** in **any of 3 reading frames**, giving **6 possible translations**:

```
PLUS strand:
  Frame 0:  A T G | G C T | G C C | ...
  Frame 1:    T G G | C T G | C C A | ...
  Frame 2:      G G C | T G C | C A T | ...

MINUS strand (reverse complement):
  Frame 0:  ... | G G C | A G C | C A T
  Frame 1:    ... | G C A | G C C | A T ...
  Frame 2:      ... | C A G | C C A | T ...
```

The algorithm:

1. **Circularise** the plasmid by concatenating it with itself (`plasmid + plasmid`). This handles genes that wrap around the origin.
2. **Translate** each of the 6 frames into protein.
3. **Align** each translation against the known WT protein using the BLOSUM62 scoring matrix.
4. **Select** the frame with the highest percent identity above the threshold (default: 60%).
5. **Validate** the candidate: CDS must be divisible by 3, no ambiguous bases, protein length ≥ 80% of reference.

### Diagram — 6-Frame Search

```
        Circular plasmid (5000 bp)
    ┌───────────────────────────────┐
    │ ▸▸▸▸▸▸ backbone ▸▸▸▸▸▸▸▸▸▸▸ │
    │                               │
    │    ┌─── YOUR GENE ───┐        │
    │    │  CDS: 1200–2400 │        │
    │    │  PLUS strand     │        │
    │    │  Frame 0         │        │
    │    └──────────────────┘        │
    │                               │
    │ ◂◂◂◂◂◂ backbone ◂◂◂◂◂◂◂◂◂◂◂ │
    └───────────────────────────────┘

          6 translations tried
    ┌──────────┐
    │ PLUS F0  │ ━━━ 98.5% identity ← BEST MATCH
    │ PLUS F1  │ ─── 12.3% identity
    │ PLUS F2  │ ─── 15.1% identity
    │ MINUS F0 │ ─── 8.7% identity
    │ MINUS F1 │ ─── 11.2% identity
    │ MINUS F2 │ ─── 9.4% identity
    └──────────┘
```

### Code Example

```python
from app.services.sequence.sequence_service import map_wt_gene_in_plasmid

# Your WT protein (from UniProt) and plasmid DNA
wt_protein = "MSKGEELFTG..."   # Full protein sequence
wt_plasmid = "ATGCGTACC..."    # Full circular plasmid

# Find the gene
mapping = map_wt_gene_in_plasmid(wt_protein, wt_plasmid)

print(f"Strand:     {mapping.strand}")          # "PLUS" or "MINUS"
print(f"Frame:      {mapping.frame}")            # 0, 1, or 2
print(f"CDS start:  {mapping.cds_start_0based}") # e.g., 1200
print(f"CDS end:    {mapping.cds_end_0based_excl}")  # e.g., 2400
print(f"Identity:   {mapping.match_identity_pct:.1f}%")  # e.g., 99.2%
print(f"CDS length: {len(mapping.wt_cds_dna)} bp")
```

### Visualisation — Plasmid Map

```python
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np

def plot_plasmid_map(mapping, plasmid_length: int):
    """
    Draws a circular plasmid map highlighting the CDS location.
    
    Args:
        mapping: WTMapping result from map_wt_gene_in_plasmid()
        plasmid_length: Total plasmid length in base pairs
    """
    fig, ax = plt.subplots(1, 1, figsize=(8, 8))
    
    # Draw plasmid circle
    circle = plt.Circle((0.5, 0.5), 0.35, fill=False, 
                         linewidth=3, color='#333333')
    ax.add_patch(circle)
    
    # Calculate CDS arc
    start_frac = mapping.cds_start_0based / plasmid_length
    end_frac = mapping.cds_end_0based_excl / plasmid_length
    
    # Draw CDS arc
    theta_start = 90 - (start_frac * 360)
    theta_end = 90 - (end_frac * 360)
    
    cds_arc = patches.Arc(
        (0.5, 0.5), 0.7, 0.7,
        angle=0,
        theta1=min(theta_start, theta_end),
        theta2=max(theta_start, theta_end),
        linewidth=8,
        color='#2196F3',
    )
    ax.add_patch(cds_arc)
    
    # Labels
    ax.text(0.5, 0.5, f"{plasmid_length} bp\nplasmid", 
            ha='center', va='center', fontsize=14, fontweight='bold')
    
    cds_len = len(mapping.wt_cds_dna) 
    mid_frac = (start_frac + end_frac) / 2
    mid_angle = np.radians(90 - mid_frac * 360)
    label_r = 0.42
    ax.text(
        0.5 + label_r * np.cos(mid_angle),
        0.5 + label_r * np.sin(mid_angle),
        f"CDS\n{cds_len} bp\n{mapping.strand} F{mapping.frame}",
        ha='center', va='center', fontsize=10,
        color='#2196F3', fontweight='bold',
    )
    
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_aspect('equal')
    ax.axis('off')
    ax.set_title(
        f"Wild-Type Plasmid Map — {mapping.match_identity_pct:.1f}% identity",
        fontsize=14, pad=20,
    )
    plt.tight_layout()
    plt.show()

# Usage:
# plot_plasmid_map(mapping, len(wt_plasmid))
```

---

## Step 2 — Variant CDS Extraction

### What Happens

Once the WT gene location is known, the pipeline uses those **same coordinates** to extract the CDS from every variant plasmid. This ensures all variants are compared to the same region.

### How It Works

```
  WT Mapping says: CDS = positions [1200, 2400), PLUS strand, frame 0

  Variant plasmid:
  ┌──────────────────────────────────────────────────┐
  │ ...backbone... │ VARIANT CDS │ ...backbone...    │
  │                │ [1200:2400) │                    │
  │                │◀── extract ─▶│                    │
  └──────────────────────────────────────────────────┘
                         │
                         ▼
              "ATGGCTGCCAAA...TAA"
              (variant CDS DNA)
```

**Key behaviours:**

- **Circular wrap-around**: If the CDS spans the plasmid origin (start > end), the extraction wraps: `plasmid[start:] + plasmid[:end]`
- **MINUS strand**: After extraction, the sequence is reverse-complemented
- **Frame offset**: Already baked into the coordinates — no additional trimming occurs

### Code Example

```python
from app.services.sequence.sequence_service import process_variant_plasmid

# Use the mapping from Step 1
result = process_variant_plasmid(
    variant_plasmid_dna="ATGCGTACC...",  # variant's full plasmid
    wt_mapping=mapping,                   # from Step 1
    fallback_search=False,
)

print(f"CDS DNA:   {result.cds_dna[:30]}...")
print(f"Protein:   {result.protein_aa[:30]}...")
print(f"Frame:     {result.frame}")
print(f"Strand:    {result.strand}")
```

### Visualisation — WT vs Variant CDS Alignment

```python
def plot_cds_comparison(wt_mapping, variant_result):
    """
    Horizontal bar chart comparing WT and variant CDS properties.
    """
    fig, axes = plt.subplots(2, 1, figsize=(12, 4), sharex=True)
    
    wt_len = len(wt_mapping.wt_cds_dna)
    var_len = len(variant_result.cds_dna) if variant_result.cds_dna else 0
    
    # DNA length comparison
    axes[0].barh(['WT', 'Variant'], [wt_len, var_len], 
                 color=['#4CAF50', '#2196F3'], height=0.5)
    axes[0].set_title('CDS Length (bp)')
    for i, v in enumerate([wt_len, var_len]):
        axes[0].text(v + 5, i, f"{v} bp", va='center')
    
    # Protein length comparison
    wt_prot_len = len(wt_mapping.wt_protein_aa)
    var_prot_len = len(variant_result.protein_aa) if variant_result.protein_aa else 0
    
    axes[1].barh(['WT', 'Variant'], [wt_prot_len, var_prot_len],
                 color=['#4CAF50', '#2196F3'], height=0.5)
    axes[1].set_title('Protein Length (aa)')
    for i, v in enumerate([wt_prot_len, var_prot_len]):
        axes[1].text(v + 1, i, f"{v} aa", va='center')
    
    plt.tight_layout()
    plt.show()

# Usage:
# plot_cds_comparison(mapping, result)
```

---

## Step 3 — Translation & Quality Control

### What Happens

After CDS extraction, the DNA is translated to protein and checked for quality issues. The QC flags help you identify problematic variants that need manual review.

### Translation Process

```
  CDS DNA:    A T G  G C T  G C C  A A A  ...  T A A
              ─┬──   ─┬──   ─┬──   ─┬──       ─┬──
Codon #:       1       2       3       4        last

Amino Acids:   M       A       A       K    ...  Stop

Protein:      "MAAK..."
```

### QC Checks Performed

```
┌─────────────────────────────────────────────────────────┐
│                    QC Checkpoint                         │
├──────────────────────────┬──────────────────────────────┤
│  Check                   │  What it detects              │
├──────────────────────────┼──────────────────────────────┤
│  len(CDS) % 3 ≠ 0       │  FRAMESHIFT — codons are      │
│                          │  misaligned, protein is        │
│                          │  scrambled downstream          │
├──────────────────────────┼──────────────────────────────┤
│  Non-ACGT bases          │  AMBIGUOUS BASES — assembly    │
│  (N, R, Y, W, S, etc.)  │  quality issue, translation    │
│                          │  may be unreliable             │
├──────────────────────────┼──────────────────────────────┤
│  Early stop codon (*)    │  PREMATURE STOP — protein is   │
│  in translated sequence  │  truncated or nonfunctional    │
└──────────────────────────┴──────────────────────────────┘
```

### Stop Codon Policies

The pipeline supports two stop codon handling modes (configured via `STOP_POLICY`):

| Policy | Behaviour | When to Use |
|--------|-----------|-------------|
| `truncate` | Stop translation at first stop codon. Flag as premature if protein is shorter than WT. | Standard protein analysis — you want the mature protein only |
| `keep_stops` | Include stop codons (`*`) in the protein sequence. Flag any internal stops. | Mutation scanning — you want to see where stops appear |

### Code Example

```python
# Inspect QC results
result = process_variant_plasmid(variant_dna, mapping, fallback_search=False)

print("=== Quality Control Report ===")
print(f"  Frameshift:      {'YES ⚠' if result.qc.has_frameshift else 'No ✓'}")
print(f"  Ambiguous bases: {'YES ⚠' if result.qc.has_ambiguous_bases else 'No ✓'}")
print(f"  Premature stop:  {'YES ⚠' if result.qc.has_premature_stop else 'No ✓'}")
if result.qc.notes:
    print(f"  Notes: {result.qc.notes}")

if result.protein_aa:
    print(f"\n  Protein ({len(result.protein_aa)} aa): {result.protein_aa[:50]}...")
else:
    print(f"\n  ⚠ Translation failed — protein_aa is None")
```

### Visualisation — QC Dashboard

```python
def plot_qc_summary(results: list):
    """
    Pie charts showing QC flag distribution across all variants.
    
    Args:
        results: List of VariantSeqResult objects
    """
    total = len(results)
    frameshifts = sum(1 for r in results if r.qc.has_frameshift)
    ambiguous = sum(1 for r in results if r.qc.has_ambiguous_bases)
    premature = sum(1 for r in results if r.qc.has_premature_stop)
    no_protein = sum(1 for r in results if r.protein_aa is None)
    clean = total - frameshifts - ambiguous - premature - no_protein
    # Deduplicate — some variants have multiple flags
    clean = max(0, total - len([
        r for r in results 
        if r.qc.has_frameshift or r.qc.has_ambiguous_bases 
        or r.qc.has_premature_stop or r.protein_aa is None
    ]))
    flagged = total - clean

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Overall pass/fail
    axes[0].pie(
        [clean, flagged],
        labels=[f'Clean ({clean})', f'Flagged ({flagged})'],
        colors=['#4CAF50', '#FF5722'],
        autopct='%1.1f%%',
        startangle=90,
        textprops={'fontsize': 12},
    )
    axes[0].set_title(f'QC Summary — {total} Variants', fontsize=14)

    # Flag breakdown
    flags = {
        'Frameshift': frameshifts,
        'Ambiguous Bases': ambiguous,
        'Premature Stop': premature,
        'No Protein': no_protein,
    }
    flag_names = [k for k, v in flags.items() if v > 0]
    flag_vals = [v for v in flags.values() if v > 0]
    
    if flag_vals:
        colors = ['#FF9800', '#F44336', '#9C27B0', '#795548']
        axes[1].barh(flag_names, flag_vals, color=colors[:len(flag_names)])
        axes[1].set_xlabel('Count')
        axes[1].set_title('QC Flag Breakdown', fontsize=14)
        for i, v in enumerate(flag_vals):
            axes[1].text(v + 0.3, i, str(v), va='center', fontweight='bold')
    else:
        axes[1].text(0.5, 0.5, 'All variants passed QC ✓',
                     ha='center', va='center', fontsize=16, color='#4CAF50')
        axes[1].axis('off')

    plt.tight_layout()
    plt.show()

# Usage:
# all_results = [process_variant_plasmid(dna, mapping, fallback_search=False) 
#                for _, dna in variants]
# plot_qc_summary(all_results)
```

---

## Step 4 — Mutation Calling

### What Happens

Each variant's CDS is compared against the WT CDS to identify and classify every mutation. The pipeline automatically selects the best strategy.

### Strategy Selection Diagram

```
                    ┌─────────────────────────┐
                    │   call_mutations_against_wt()   │
                    │   (variant CDS vs WT CDS)       │
                    └──────────────┬──────────────────┘
                                   │
                    ┌──────────────▼──────────────────┐
                    │  Either CDS length % 3 ≠ 0?     │
                    └──────┬───────────────┬──────────┘
                           │ YES           │ NO
                           ▼               ▼
               ┌───────────────┐   ┌──────────────────┐
               │  FRAMESHIFT   │   │  Same length?     │
               │  (1 record)   │   └───┬──────────┬───┘
               └───────────────┘       │ YES      │ NO
                                       ▼          ▼
                            ┌──────────────┐  ┌──────────────────┐
                            │  Codon-by-   │  │  Protein         │
                            │  codon       │  │  alignment       │
                            │  comparison  │  │  (BLOSUM62)      │
                            │  ▸▸ FAST ▸▸  │  │  ▸▸ INDELS ▸▸   │
                            └──────────────┘  └──────────────────┘
```

### Codon-by-Codon Comparison (Same-Length Sequences)

```
Position:  1     2     3     4     5     6     7
WT:       ATG   GCT   GCC   AAA   GAT   TTG   TAA
Variant:  ATG   GCT   GCC   AAG   GAT   TTG   TAA
                             ^^^
                     Codon 4: AAA → AAG
                     AA:      Lys → Lys
                     Type:    SYNONYMOUS
                     (Same amino acid, different codon)
```

### Protein Alignment (Different-Length Sequences — Indels)

```
WT protein:      M  A  A  K  D  L  *
Variant protein: M  A  A  R  K  D  L  *
                          ↑
                    INSERTION at position 4
                    New residue: R (Arg)

Alignment:
  WT:   M  A  A  -  K  D  L  *
  Var:  M  A  A  R  K  D  L  *
                 ↑
              gap in WT = INSERTION in variant
```

### Code Example

```python
from app.services.sequence.sequence_service import call_mutations_against_wt

# Compare variant CDS to WT CDS
mutations, counts = call_mutations_against_wt(
    wt_cds_dna=mapping.wt_cds_dna,    # from Step 1
    var_cds_dna=result.cds_dna,         # from Step 2
)

# Summary
print(f"Total mutations:     {counts.total}")
print(f"  Synonymous:        {counts.synonymous}")
print(f"  Nonsynonymous:     {counts.nonsynonymous}")

# Detailed mutation list
print(f"\n{'Type':<16} {'Pos':>4}  {'WT':>3} → {'Var':>3}  {'WT Codon':>9} → {'Var Codon'}")
print(f"{'─'*16} {'─'*4}  {'─'*3}   {'─'*3}  {'─'*9}   {'─'*9}")
for m in mutations:
    pos = m.aa_position_1based or "-"
    wt_aa = m.wt_aa or "-"
    var_aa = m.var_aa or "-"
    wt_c = m.wt_codon or "-"
    var_c = m.var_codon or "-"
    print(f"{m.mutation_type:<16} {str(pos):>4}  {wt_aa:>3} → {var_aa:>3}  {wt_c:>9} → {var_c}")
```

### Visualisation — Mutation Spectrum

```python
def plot_mutation_spectrum(mutations_by_variant: dict):
    """
    Stacked bar chart showing mutation type distribution per variant.
    
    Args:
        mutations_by_variant: Dict of {variant_id: List[MutationRecord]}
    """
    import matplotlib.pyplot as plt
    from collections import Counter
    
    type_colors = {
        'SYNONYMOUS': '#4CAF50',
        'NONSYNONYMOUS': '#FF9800',
        'NONSENSE': '#F44336',
        'FRAMESHIFT': '#9C27B0',
        'INSERTION': '#2196F3',
        'DELETION': '#00BCD4',
        'AMBIGUOUS': '#9E9E9E',
    }
    
    variant_ids = list(mutations_by_variant.keys())
    all_types = list(type_colors.keys())
    
    # Count each type per variant
    data = {}
    for mtype in all_types:
        data[mtype] = [
            sum(1 for m in mutations_by_variant[vid] if m.mutation_type == mtype)
            for vid in variant_ids
        ]
    
    fig, ax = plt.subplots(figsize=(max(8, len(variant_ids) * 0.4), 6))
    
    x = range(len(variant_ids))
    bottom = [0] * len(variant_ids)
    
    for mtype in all_types:
        vals = data[mtype]
        if any(v > 0 for v in vals):
            ax.bar(x, vals, bottom=bottom, label=mtype, 
                   color=type_colors[mtype], width=0.7)
            bottom = [b + v for b, v in zip(bottom, vals)]
    
    ax.set_xlabel('Variant ID', fontsize=12)
    ax.set_ylabel('Mutation Count', fontsize=12)
    ax.set_title('Mutation Spectrum by Variant', fontsize=14)
    ax.set_xticks(x)
    ax.set_xticklabels(variant_ids, rotation=45, ha='right')
    ax.legend(loc='upper right')
    plt.tight_layout()
    plt.show()

# Usage:
# mutations_dict = {}
# for vid, dna in variants:
#     res = process_variant_plasmid(dna, mapping, fallback_search=False)
#     if res.cds_dna:
#         muts, _ = call_mutations_against_wt(mapping.wt_cds_dna, res.cds_dna)
#         mutations_dict[vid] = muts
# plot_mutation_spectrum(mutations_dict)
```

### Visualisation — Mutation Heatmap (Position × Variant)

```python
def plot_mutation_heatmap(mutations_by_variant: dict, wt_protein_length: int):
    """
    Heatmap showing which positions are mutated across variants.
    Rows = variants, columns = amino acid positions.
    
    Args:
        mutations_by_variant: Dict of {variant_id: List[MutationRecord]}
        wt_protein_length: Length of WT protein in amino acids
    """
    import numpy as np
    
    variant_ids = sorted(mutations_by_variant.keys())
    
    # Encode: 0=WT, 1=SYN, 2=NONSYN, 3=NONSENSE
    type_to_val = {
        'SYNONYMOUS': 1, 'NONSYNONYMOUS': 2,
        'NONSENSE': 3, 'INSERTION': 2, 'DELETION': 2,
    }
    
    matrix = np.zeros((len(variant_ids), wt_protein_length))
    
    for row, vid in enumerate(variant_ids):
        for m in mutations_by_variant[vid]:
            pos = m.aa_position_1based
            if pos and 1 <= pos <= wt_protein_length:
                matrix[row, pos - 1] = type_to_val.get(m.mutation_type, 0)
    
    fig, ax = plt.subplots(figsize=(min(20, wt_protein_length * 0.08), 
                                     max(4, len(variant_ids) * 0.3)))
    
    from matplotlib.colors import ListedColormap
    cmap = ListedColormap(['#FFFFFF', '#A5D6A7', '#FFB74D', '#E57373'])
    
    im = ax.imshow(matrix, aspect='auto', cmap=cmap, vmin=0, vmax=3)
    
    ax.set_xlabel('Amino Acid Position', fontsize=12)
    ax.set_ylabel('Variant', fontsize=12)
    ax.set_title('Mutation Heatmap', fontsize=14)
    ax.set_yticks(range(len(variant_ids)))
    ax.set_yticklabels(variant_ids, fontsize=8)
    
    # Legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='#FFFFFF', edgecolor='#CCC', label='Wild-type'),
        Patch(facecolor='#A5D6A7', label='Synonymous'),
        Patch(facecolor='#FFB74D', label='Nonsynonymous'),
        Patch(facecolor='#E57373', label='Nonsense'),
    ]
    ax.legend(handles=legend_elements, loc='upper right', fontsize=9)
    
    plt.tight_layout()
    plt.show()

# Usage:
# plot_mutation_heatmap(mutations_dict, len(mapping.wt_protein_aa))
```

---

## Step 5 — Interpreting Results

### Experiment Status

After all variants are processed, the experiment receives a final status:

| Status | Meaning | Action |
|--------|---------|--------|
| **ANALYSED** | All variants processed successfully, no QC issues | Results are ready for analysis |
| **ANALYSED_WITH_ERRORS** | Processing completed but some variants had issues (frameshift, premature stop, failed translation, or exceptions) | Review flagged variants — most results are still valid |
| **FAILED** | Fatal pipeline error (e.g., WT mapping failed, database unreachable) | Check logs, fix the issue, re-run |

### Understanding Your Mutation Counts

```
┌──────────────────────────────────────────────────────────┐
│  Experiment Summary                                       │
│                                                           │
│  Total variants:          150                             │
│  With mutations:          142  (94.7%)                    │
│  WT-identical:              8  ( 5.3%)                    │
│                                                           │
│  Mutation breakdown:                                      │
│  ┌────────────────────┬──────┬───────────┐               │
│  │ Type               │ Count│ % of Total│               │
│  ├────────────────────┼──────┼───────────┤               │
│  │ Synonymous         │  387 │   62.3%   │               │
│  │ Nonsynonymous      │  198 │   31.9%   │               │
│  │ Nonsense (stop)    │   12 │    1.9%   │               │
│  │ Frameshift         │    5 │    0.8%   │               │
│  │ Insertion          │    8 │    1.3%   │               │
│  │ Deletion           │   11 │    1.8%   │               │
│  └────────────────────┴──────┴───────────┘               │
└──────────────────────────────────────────────────────────┘
```

### Visualisation — Experiment Summary Dashboard

```python
def plot_experiment_dashboard(all_results: list, all_mutations: dict):
    """
    Full experiment summary: status pie, mutation totals, protein length distribution.
    
    Args:
        all_results: List of VariantSeqResult for all variants
        all_mutations: Dict of {variant_id: MutationCounts}
    """
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    
    # Panel 1: Variant status
    clean = sum(1 for r in all_results 
                if r.protein_aa and not r.qc.has_frameshift 
                and not r.qc.has_premature_stop)
    flagged = len(all_results) - clean
    axes[0].pie([clean, flagged], 
                labels=[f'Clean\n({clean})', f'Flagged\n({flagged})'],
                colors=['#4CAF50', '#FF5722'], autopct='%1.0f%%',
                textprops={'fontsize': 11})
    axes[0].set_title('Variant QC Status', fontsize=13)
    
    # Panel 2: Total mutations by type
    from collections import Counter
    type_counts = Counter()
    for vid, muts in all_mutations.items():
        for m in muts:
            type_counts[m.mutation_type] += 1
    
    if type_counts:
        type_colors_map = {
            'SYNONYMOUS': '#4CAF50', 'NONSYNONYMOUS': '#FF9800',
            'NONSENSE': '#F44336', 'FRAMESHIFT': '#9C27B0',
            'INSERTION': '#2196F3', 'DELETION': '#00BCD4',
            'AMBIGUOUS': '#9E9E9E',
        }
        labels = list(type_counts.keys())
        vals = list(type_counts.values())
        colors = [type_colors_map.get(l, '#999') for l in labels]
        axes[1].barh(labels, vals, color=colors)
        axes[1].set_xlabel('Count')
        axes[1].set_title('Total Mutations by Type', fontsize=13)
        for i, v in enumerate(vals):
            axes[1].text(v + 0.5, i, str(v), va='center', fontsize=10)
    
    # Panel 3: Protein length distribution
    prot_lengths = [len(r.protein_aa) for r in all_results if r.protein_aa]
    if prot_lengths:
        axes[2].hist(prot_lengths, bins=30, color='#2196F3', edgecolor='white')
        axes[2].axvline(prot_lengths[0], color='red', linestyle='--', 
                        label='WT length')
        axes[2].set_xlabel('Protein Length (aa)')
        axes[2].set_ylabel('Count')
        axes[2].set_title('Protein Length Distribution', fontsize=13)
        axes[2].legend()
    
    plt.suptitle('Experiment Analysis Dashboard', fontsize=16, y=1.02)
    plt.tight_layout()
    plt.show()

# Usage:
# plot_experiment_dashboard(all_results, mutations_dict) 
```

---

## Visualisation Code Examples

### Complete End-to-End Example

This code runs the full pipeline on 5 variants and generates all visualisations:

```python
from app.services.sequence.db_repo import (
    get_engine, get_wt_reference, list_variants_by_experiment,
)
from app.services.sequence.sequence_service import (
    map_wt_gene_in_plasmid,
    process_variant_plasmid,
    call_mutations_against_wt,
)
import matplotlib.pyplot as plt

# ── Configuration ──
EXPERIMENT_ID = 41
MAX_VARIANTS = 5

# ── Step 1: Load references & map WT ──
engine = get_engine()
wt_protein, wt_plasmid = get_wt_reference(engine, EXPERIMENT_ID)
mapping = map_wt_gene_in_plasmid(wt_protein, wt_plasmid)

print(f"WT Mapping: {mapping.strand} strand, frame {mapping.frame}")
print(f"CDS: [{mapping.cds_start_0based}, {mapping.cds_end_0based_excl})")
print(f"Identity: {mapping.match_identity_pct:.1f}%")

# ── Steps 2–4: Process variants ──
variants = list_variants_by_experiment(engine, EXPERIMENT_ID)[:MAX_VARIANTS]
results = []
mutations_dict = {}

for vid, dna in variants:
    res = process_variant_plasmid(dna, mapping, fallback_search=False)
    results.append(res)
    
    if res.cds_dna and mapping.wt_cds_dna:
        muts, counts = call_mutations_against_wt(mapping.wt_cds_dna, res.cds_dna)
        mutations_dict[vid] = muts
        print(f"Variant {vid}: {counts.total} mutations "
              f"({counts.synonymous} syn, {counts.nonsynonymous} nonsyn)")
    else:
        mutations_dict[vid] = []
        print(f"Variant {vid}: No CDS extracted")

# ── Step 5: Generate visualisations ──
# (Call any of the plot_* functions defined above)
# plot_plasmid_map(mapping, len(wt_plasmid))
# plot_qc_summary(results)
# plot_mutation_spectrum(mutations_dict)
# plot_mutation_heatmap(mutations_dict, len(mapping.wt_protein_aa))
# plot_experiment_dashboard(results, mutations_dict)
```

### Exporting Results to CSV

```python
import csv

def export_mutations_csv(mutations_dict: dict, output_path: str):
    """Export all mutations to a CSV file for downstream analysis."""
    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow([
            'variant_id', 'mutation_type', 'aa_position',
            'wt_aa', 'var_aa', 'wt_codon', 'var_codon', 'notes',
        ])
        for vid, muts in sorted(mutations_dict.items()):
            for m in muts:
                writer.writerow([
                    vid, m.mutation_type, m.aa_position_1based,
                    m.wt_aa, m.var_aa, m.wt_codon, m.var_codon, m.notes,
                ])
    print(f"Exported {sum(len(m) for m in mutations_dict.values())} mutations to {output_path}")

# Usage:
# export_mutations_csv(mutations_dict, "experiment_41_mutations.csv")
```

---

## Troubleshooting & QC Flags

### Common Issues

!!! warning "Frameshift Detected"
    **Symptom**: `qc.has_frameshift = True`, mutation type is `FRAMESHIFT`  
    **Cause**: Variant CDS length is not divisible by 3. Usually caused by an insertion or deletion of 1–2 bases (not a multiple of 3).  
    **Impact**: The protein downstream of the frameshift is completely scrambled. Mutation calling cannot be performed.  
    **Action**: Check the assembly quality. If the variant truly has a frameshift, it likely produces a nonfunctional protein.

!!! warning "Premature Stop Codon"
    **Symptom**: `qc.has_premature_stop = True`, variant protein is shorter than WT  
    **Cause**: A nonsense mutation introduced a stop codon partway through the gene.  
    **Impact**: Protein is truncated. May still be partially functional depending on where the stop occurs.  
    **Action**: Check the mutation report for NONSENSE-type mutations to see the exact position.

!!! warning "Ambiguous Bases"
    **Symptom**: `qc.has_ambiguous_bases = True`  
    **Cause**: The assembled DNA contains N, R, Y, or other IUPAC ambiguity codes, typically from low-coverage regions in sequencing.  
    **Impact**: Translation may be unreliable. Codons with ambiguous bases are classified as AMBIGUOUS mutations.  
    **Action**: Check sequencing coverage at the CDS region. Consider re-sequencing the variant.

!!! danger "Translation Failed (protein_aa is None)"
    **Symptom**: `result.protein_aa is None`  
    **Cause**: Biopython could not translate the CDS (e.g., invalid bases, empty CDS).  
    **Impact**: No protein sequence available. Variant is recorded with QC-only data.  
    **Action**: Inspect `result.qc.notes` for the specific error message.

!!! info "No CDS Extracted"
    **Symptom**: `result.cds_dna is None` or empty string  
    **Cause**: The variant plasmid may be truncated, or the CDS coordinates fall outside the sequence.  
    **Impact**: Cannot process this variant at all.  
    **Action**: Verify the variant's assembled DNA sequence covers the full plasmid.

### Experiment Status Decision Tree

```
                    All variants processed?
                    ┌────────┴────────┐
                    │ NO              │ YES
                    ▼                 │
              ┌──────────┐           │
              │  FAILED   │           │
              └──────────┘           ▼
                            Any variant had:
                           • exception?
                           • frameshift?
                           • premature stop?
                           • protein_aa = None?
                           • empty CDS?
                    ┌────────┴────────┐
                    │ YES             │ NO
                    ▼                 ▼
        ┌───────────────────┐  ┌───────────┐
        │ ANALYSED_WITH_    │  │ ANALYSED  │
        │ ERRORS            │  │           │
        └───────────────────┘  └───────────┘
```
