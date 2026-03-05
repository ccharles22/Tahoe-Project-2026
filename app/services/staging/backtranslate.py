"""Back-translation utilities for staging workflows.

Provides amino-acid-to-codon conversion using the standard genetic code.
Used by the staging pipeline to synthesise plausible CDS sequences from
protein inputs when no DNA template is available.
"""

from __future__ import annotations

import random

# Standard genetic code: each amino acid mapped to all synonymous codons.
AA_TO_CODONS = {
    'A': ['GCT', 'GCC', 'GCA', 'GCG'],
    'C': ['TGT', 'TGC'],
    'D': ['GAT', 'GAC'],
    'E': ['GAA', 'GAG'],
    'F': ['TTT', 'TTC'],
    'G': ['GGT', 'GGC', 'GGA', 'GGG'],
    'H': ['CAT', 'CAC'],
    'I': ['ATT', 'ATC', 'ATA'],
    'K': ['AAA', 'AAG'],
    'L': ['TTA', 'TTG', 'CTT', 'CTC', 'CTA', 'CTG'],
    'M': ['ATG'],
    'N': ['AAT', 'AAC'],
    'P': ['CCT', 'CCC', 'CCA', 'CCG'],
    'Q': ['CAA', 'CAG'],
    'R': ['CGT', 'CGC', 'CGA', 'CGG', 'AGA', 'AGG'],
    'S': ['TCT', 'TCC', 'TCA', 'TCG', 'AGT', 'AGC'],
    'T': ['ACT', 'ACC', 'ACA', 'ACG'],
    'V': ['GTT', 'GTC', 'GTA', 'GTG'],
    'W': ['TGG'],
    'Y': ['TAT', 'TAC'],
    '*': ['TAA', 'TAG', 'TGA'],
}


def backtranslate(protein: str) -> str:
    """Create a plausible DNA coding sequence from an amino-acid sequence.

    Randomly selects one synonymous codon per residue.  Unknown residues
    (``X``) map to ``NNN`` to preserve reading-frame alignment.

    Args:
        protein: Amino-acid sequence (case-insensitive, whitespace-tolerant).

    Returns:
        str: DNA sequence whose length equals ``3 * len(protein.strip())``.
    """
    protein = protein.strip().upper()
    dna = []
    for aa in protein:
        if aa == 'X':
            dna.append('NNN')
            continue
        codons = AA_TO_CODONS.get(aa)
        dna.append(random.choice(codons) if codons else 'NNN')
    return ''.join(dna)
