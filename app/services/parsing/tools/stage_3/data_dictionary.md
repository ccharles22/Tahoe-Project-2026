# Data Dictionary – BSU Polymerase Dataset

## TSV Column Names (exact case):
- Plasmid_Variant_Index
- Parent_Plasmid_Variant
- Directed_Evolution_Generation
- Assembled_DNA_Sequence
- DNA_Quantification_fg
- Protein_Quantification_pg
- Control

## JSON Structure:
- Root element is an array of objects
- JSON field names exactly match TSV column names (case-sensitive)
- No nesting observed

## Value Ranges:
- DNA_Quantification_fg: min=389.21, max=2000.0, negatives=0
- Protein_Quantification_pg: min=36.52, max=70.46, negatives=0
- Sequence length: min=7823, max=7838
- Directed_Evolution_Generation: 0–10
- Total records: 301

## Data Quality Observations:
- No negative or missing DNA/Protein quantification values observed
- Directed evolution generations span 0–10
- Sequence lengths are highly consistent (variation of 15 bp)
- Parent_Plasmid_Variant uses -1 for generation 0 entries
- TSV and JSON schemas are identical (field names and casing)
