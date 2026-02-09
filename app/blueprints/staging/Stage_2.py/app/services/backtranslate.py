import random

AA_TO_CODONS = {
    "A":["GCT","GCC","GCA","GCG"],
    "C":["TGT","TGC"],
    "D":["GAT","GAC"],
    "E":["GAA","GAG"],
    "F":["TTT","TTC"],
    "G":["GGT","GGC","GGA","GGG"],
    "H":["CAT","CAC"],
    "I":["ATT","ATC","ATA"],
    "K":["AAA","AAG"],
    "L":["TTA","TTG","CTT","CTC","CTA","CTG"],
    "M":["ATG"],
    "N":["AAT","AAC"],
    "P":["CCT","CCC","CCA","CCG"],
    "Q":["CAA","CAG"],
    "R":["CGT","CGC","CGA","CGG","AGA","AGG"],
    "S":["TCT","TCC","TCA","TCG","AGT","AGC"],
    "T":["ACT","ACC","ACA","ACG"],
    "V":["GTT","GTC","GTA","GTG"],
    "W":["TGG"],
    "Y":["TAT","TAC"],
    "*":["TAA","TAG","TGA"]
}

def backtranslate(protein: str) -> str:
    protein = protein.strip().upper()
    dna = []
    for aa in protein:
        if aa == 'X':
            dna.append('NNN')
            continue
        codons = AA_TO_CODONS.get(aa)
        if not codons:
            dna.append('NNN')
        else:
            dna.append(random.choice(codons))
    return "".join(dna)
