"""
Configuration for data parsing and quality control.
Designed to be adjustable for different datasets.
"""

# =========================
# Standardized field names
# =========================

# Required fields – must exist after normalization
REQUIRED_FIELDS = [
    "variant_index",
    "generation",
    "assembled_dna_sequence",
    "dna_yield",
    "protein_yield",
]

# Optional fields
OPTIONAL_FIELDS = [
    "parent_variant_index",  # -1 or NULL for generation 0
    "control",
]

# ==================================
# Field name mapping (source → standard)
# ==================================
# Format: standard_name: [possible source names]

FIELD_MAPPING = {
    "variant_index": [
        "Plasmid_Variant_Index",
        "variant_index",
        "variant_id",
        "id",
    ],
    "parent_variant_index": [
        "Parent_Plasmid_Variant",
        "parent_variant_index",
        "parent_id",
    ],
    "generation": [
        "Directed_Evolution_Generation",
        "generation",
        "gen",
        "round",
    ],
    "assembled_dna_sequence": [
        "Assembled_DNA_Sequence",
        "sequence",
        "dna_sequence",
        "plasmid_sequence",
    ],
    "dna_yield": [
        "DNA_Quantification_fg",
        "dna_yield",
        "dna_concentration",
    ],
    "protein_yield": [
        "Protein_Quantification_pg",
        "protein_yield",
        "protein_concentration",
    ],
    "control": [
        "Control",
        "control",
        "is_control",
    ],
}

# =========================
# Validation rules
# =========================

VALIDATION_RULES = {
    "sequence_min_length": 100,
    "sequence_max_length": 50000,
    "yield_min_warning": 0.0,
    "yield_max_warning": 10000.0,
    "allowed_dna_chars": set("ATGCNatgcn"),
    "min_identity_threshold": 0.98,  # reserved for later
}

# =========================
# Error vs Warning behavior
# =========================

ERROR_THRESHOLDS = {
    "missing_required_field": True,
    "invalid_data_type": True,
    "invalid_dna_sequence": True,
    "empty_sequence": True,
}

WARNING_THRESHOLDS = {
    "negative_yield": True,
    "extreme_yield": True,
    "frameshift_sequence": True,
    "unusual_sequence_length": True,
}
