import pandas as pd

df = pd.read_csv(
    "data/DE_BSU_Pol_Batch_1.tsv",
    sep="\t"
)

print("DNA fg min/max:", df["DNA_Quantification_fg"].min(), df["DNA_Quantification_fg"].max())
print("Protein pg min/max:", df["Protein_Quantification_pg"].min(), df["Protein_Quantification_pg"].max())

print("Negative DNA:", (df["DNA_Quantification_fg"] < 0).sum())
print("Negative Protein:", (df["Protein_Quantification_pg"] < 0).sum())

print("Total records:", len(df))
seq_lengths = df["Assembled_DNA_Sequence"].str.len()

print("Seq length min/max:", seq_lengths.min(), seq_lengths.max())
print(sorted(df["Directed_Evolution_Generation"].unique()))
