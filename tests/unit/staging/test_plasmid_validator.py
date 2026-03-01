"""Unit tests for staging plasmid validation."""

import pytest
from Bio.Data.CodonTable import TranslationError

from app.services.staging.plasmid_validator import translate_frame, validate_plasmid


def test_validate_plasmid_passes_on_exact_encoding():
    # MKT encoded by ATG AAA ACC
    protein = "MKT"
    plasmid = "GGGATGAAAACCTTT"
    result = validate_plasmid(protein, plasmid)

    assert result.is_valid is True
    assert result.identity == 100.0
    assert result.coverage == 100.0
    assert result.wraps is False


def test_validate_plasmid_detects_circular_wrap():
    # Gene start is near end and wraps to plasmid start.
    protein = "MKT"
    plasmid = "AAAACCGGGGGGATG"
    result = validate_plasmid(protein, plasmid)

    assert result.is_valid is True
    assert result.wraps is True
    assert result.start_nt == 12
    assert result.end_nt == 5


def test_validate_plasmid_fails_when_no_exact_encoding():
    protein = "MMMM"
    plasmid = "ACGTACGTACGT"
    result = validate_plasmid(protein, plasmid)

    assert result.is_valid is False
    assert "No exact WT protein encoding found" in result.message


def test_validate_plasmid_uses_pipeline_default_genetic_code_table_11():
    protein = "MKT"
    plasmid = "ATGAAAACC"
    result = validate_plasmid(protein, plasmid)

    assert result.is_valid is True
    assert result.identity == 100.0
    assert result.coverage == 100.0
    assert result.genetic_code_used == 11


def test_translate_frame_allows_explicit_table_override():
    # With CDS semantics, GTG is a valid start codon in table 11, but not in table 1.
    dna = "GTGAAATAA"
    assert translate_frame(dna, frame=0, genetic_code_table=11, cds=True) == "MK"
    with pytest.raises(TranslationError):
        translate_frame(dna, frame=0, genetic_code_table=1, cds=True)

