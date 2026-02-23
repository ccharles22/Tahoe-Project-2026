"""Back-translation utilities for staging workflows."""

from __future__ import annotations

import random

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

    Unknown residues map to ``NNN`` to keep output length aligned to input.
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
