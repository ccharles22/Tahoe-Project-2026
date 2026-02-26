"""Unit tests for staging FASTA upload parsing."""

import pytest

from app.services.staging.parse_fasta import parse_fasta


def test_parse_fasta_accepts_iupac_ambiguity_codes():
    fasta = b">plasmid\nACGTRYSWKMBDHVN\n"
    assert parse_fasta(fasta) == "ACGTRYSWKMBDHVN"


def test_parse_fasta_normalises_rna_u_to_t():
    fasta = b">plasmid\nAUGCAU\n"
    assert parse_fasta(fasta) == "ATGCAT"


def test_parse_fasta_rejects_invalid_symbols():
    fasta = b">plasmid\nACGTZ\n"
    with pytest.raises(ValueError, match="Invalid characters"):
        parse_fasta(fasta)

