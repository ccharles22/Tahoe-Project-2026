"""
Tests for app.services.sequence.uniprot_service
Covers:
- Accession validation (_clean_accession)
- FASTA parsing (_parse_fasta_sequence)
- JSON sequence/feature extraction
- HTTP helpers with mocked responses
- Public API functions with mocked network
- _safe_get utility
- _is_retryable logic

"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.services.sequence.uniprot_service import (
    AMINO_ACID_PATTERN,
    UniProtEntry,
    UniProtFeature,
    UniProtRetrievalError,
    acquire_uniprot_entry_with_features,
    acquire_uniprot_protein_fasta,
    _clean_accession,
    _extract_features_from_json,
    _extract_sequence_from_json,
    _is_retryable,
    _parse_fasta_sequence,
    _raise_for_uniprot_status,
    _safe_get,
)


# ============================================================================
# Fixtures
# ============================================================================

SAMPLE_FASTA = """>sp|P12345|EXAMPLE Protein OS=Homo sapiens
MVLSPADKTNVKAAWGKVGAHAGEYGAEALERMFLSFPTTKTYFPHFDLSH
GSAQVKGHGKKVADALTNAVAHVDDMPNALSALSDLHAHKLRVDPVNFKLL
"""

SAMPLE_JSON = {
    "primaryAccession": "P12345",
    "sequence": {"value": "MVLSPADKTNVKAAWGKVGAHAGEYGAEAL", "length": 30},
    "proteinDescription": {
        "recommendedName": {"fullName": {"value": "Hemoglobin subunit alpha"}},
    },
    "genes": [{"geneName": {"value": "HBA1"}}],
    "organism": {"scientificName": "Homo sapiens"},
    "features": [
        {
            "type": "Chain",
            "description": "Hemoglobin subunit alpha",
            "location": {"start": {"value": 1}, "end": {"value": 142}},
            "evidences": [{"evidenceCode": "ECO:0000269"}],
        },
        {
            "type": "Active site",
            "description": "Catalytic residue",
            "location": {"start": {"value": 87}, "end": {"value": 87}},
        },
    ],
}


# ============================================================================
# _clean_accession
# ============================================================================


class TestCleanAccession:
    def test_valid_accession(self):
        assert _clean_accession("P12345") == "P12345"

    def test_lowercase_normalised(self):
        assert _clean_accession("p12345") == "P12345"

    def test_whitespace_stripped(self):
        assert _clean_accession("  P12345  ") == "P12345"

    def test_empty_raises(self):
        with pytest.raises(UniProtRetrievalError, match="non-empty"):
            _clean_accession("")

    def test_none_raises(self):
        with pytest.raises(UniProtRetrievalError, match="non-empty"):
            _clean_accession(None)

    def test_invalid_chars_raises(self):
        with pytest.raises(UniProtRetrievalError, match="Invalid"):
            _clean_accession("P-12345!")

    def test_too_short_raises(self):
        with pytest.raises(UniProtRetrievalError, match="Invalid"):
            _clean_accession("AB")


# ============================================================================
# _parse_fasta_sequence
# ============================================================================


class TestParseFastaSequence:
    def test_standard_fasta(self):
        seq = _parse_fasta_sequence(SAMPLE_FASTA)
        assert seq.startswith("MVLSPADKTNV")
        assert "\n" not in seq
        assert ">" not in seq

    def test_empty_string(self):
        assert _parse_fasta_sequence("") == ""

    def test_no_header(self):
        assert _parse_fasta_sequence("MVLSPADKTNV") == ""

    def test_header_only(self):
        assert _parse_fasta_sequence(">sp|P12345|TEST\n") == ""

    def test_multiline_sequence(self):
        fasta = ">header\nABC\nDEF\nGHI\n"
        assert _parse_fasta_sequence(fasta) == "ABCDEFGHI"


# ============================================================================
# _extract_sequence_from_json
# ============================================================================


class TestExtractSequenceFromJson:
    def test_valid_json(self):
        seq = _extract_sequence_from_json(SAMPLE_JSON)
        assert seq == "MVLSPADKTNVKAAWGKVGAHAGEYGAEAL"

    def test_missing_sequence_key(self):
        assert _extract_sequence_from_json({}) == ""

    def test_missing_value(self):
        assert _extract_sequence_from_json({"sequence": {}}) == ""

    def test_non_string_value(self):
        assert _extract_sequence_from_json({"sequence": {"value": 12345}}) == ""


# ============================================================================
# _extract_features_from_json
# ============================================================================


class TestExtractFeaturesFromJson:
    def test_valid_features(self):
        features = list(_extract_features_from_json(SAMPLE_JSON["features"]))
        assert len(features) == 2

        chain = features[0]
        assert chain.feature_type == "Chain"
        assert chain.begin == 1
        assert chain.end == 142
        assert chain.evidence == "ECO:0000269"

    def test_feature_without_evidence(self):
        features = list(_extract_features_from_json(SAMPLE_JSON["features"]))
        active_site = features[1]
        assert active_site.feature_type == "Active site"
        assert active_site.evidence is None

    def test_skips_non_dict(self):
        features = list(_extract_features_from_json(["not_a_dict", 42]))
        assert features == []

    def test_skips_missing_type(self):
        features = list(_extract_features_from_json([{"description": "no type"}]))
        assert features == []

    def test_empty_list(self):
        assert list(_extract_features_from_json([])) == []


# ============================================================================
# _safe_get
# ============================================================================


class TestSafeGet:
    def test_nested_dict(self):
        data = {"a": {"b": {"c": 42}}}
        assert _safe_get(data, ("a", "b", "c")) == 42

    def test_nested_list(self):
        data = {"items": [{"name": "first"}, {"name": "second"}]}
        assert _safe_get(data, ("items", 1, "name")) == "second"

    def test_missing_key(self):
        assert _safe_get({"a": 1}, ("b",)) is None

    def test_index_out_of_range(self):
        assert _safe_get({"items": [1]}, ("items", 5)) is None

    def test_empty_path(self):
        data = {"a": 1}
        assert _safe_get(data, ()) == data


# ============================================================================
# _raise_for_uniprot_status
# ============================================================================


class TestRaiseForUniprotStatus:
    def _mock_resp(self, code: int) -> MagicMock:
        resp = MagicMock(spec=requests.Response)
        resp.status_code = code
        return resp

    def test_200_ok(self):
        _raise_for_uniprot_status(self._mock_resp(200))  # should not raise

    def test_404_raises(self):
        with pytest.raises(UniProtRetrievalError, match="404"):
            _raise_for_uniprot_status(self._mock_resp(404))

    def test_429_raises(self):
        with pytest.raises(UniProtRetrievalError, match="429"):
            _raise_for_uniprot_status(self._mock_resp(429))

    def test_500_raises(self):
        with pytest.raises(UniProtRetrievalError, match="500"):
            _raise_for_uniprot_status(self._mock_resp(500))

    def test_403_raises(self):
        with pytest.raises(UniProtRetrievalError, match="403"):
            _raise_for_uniprot_status(self._mock_resp(403))


# ============================================================================
# _is_retryable
# ============================================================================


class TestIsRetryable:
    def test_rate_limit_is_retryable(self):
        exc = UniProtRetrievalError("UniProt rate limit exceeded (HTTP 429).")
        assert _is_retryable(exc) is True

    def test_server_error_is_retryable(self):
        exc = UniProtRetrievalError("UniProt server error (HTTP 500).")
        assert _is_retryable(exc) is True

    def test_404_not_retryable(self):
        exc = UniProtRetrievalError("UniProt accession not found (HTTP 404).")
        assert _is_retryable(exc) is False

    def test_network_error_is_retryable(self):
        exc = requests.ConnectionError("Connection refused")
        assert _is_retryable(exc) is True


# ============================================================================
# AMINO_ACID_PATTERN
# ============================================================================


class TestAminoAcidPattern:
    def test_standard_amino_acids(self):
        assert AMINO_ACID_PATTERN.match("ACDEFGHIKLMNPQRSTVWY")

    def test_ambiguity_codes(self):
        assert AMINO_ACID_PATTERN.match("XBZJUO")

    def test_stop_codon(self):
        assert AMINO_ACID_PATTERN.match("MVLSPA*")

    def test_lowercase_fails(self):
        assert not AMINO_ACID_PATTERN.match("mvlspa")

    def test_digits_fail(self):
        assert not AMINO_ACID_PATTERN.match("ABC123")

    def test_empty_fails(self):
        assert not AMINO_ACID_PATTERN.match("")


# ============================================================================
# acquire_uniprot_protein_fasta (mocked HTTP)
# ============================================================================


class TestAcquireUniprotProteinFasta:
    @patch("app.services.sequence.uniprot_service._http_get_text")
    def test_success(self, mock_get):
        mock_get.return_value = SAMPLE_FASTA
        seq = acquire_uniprot_protein_fasta("P12345")
        assert seq.startswith("MVLSPADKTNV")
        assert mock_get.called

    @patch("app.services.sequence.uniprot_service._http_get_text")
    def test_invalid_accession(self, mock_get):
        with pytest.raises(UniProtRetrievalError, match="Invalid"):
            acquire_uniprot_protein_fasta("!!!")

    @patch("app.services.sequence.uniprot_service._http_get_text")
    def test_empty_fasta_raises(self, mock_get):
        mock_get.return_value = ">header\n"
        with pytest.raises(UniProtRetrievalError, match="Failed to parse"):
            acquire_uniprot_protein_fasta("P12345")

    @patch("app.services.sequence.uniprot_service._http_get_text")
    def test_invalid_sequence_characters(self, mock_get):
        mock_get.return_value = ">header\n12345INVALID\n"
        with pytest.raises(UniProtRetrievalError, match="Invalid protein sequence"):
            acquire_uniprot_protein_fasta("P12345")


# ============================================================================
# acquire_uniprot_entry_with_features (mocked HTTP)
# ============================================================================


class TestAcquireUniprotEntryWithFeatures:
    @patch("app.services.sequence.uniprot_service._http_get_json")
    def test_success(self, mock_json):
        mock_json.return_value = SAMPLE_JSON
        entry = acquire_uniprot_entry_with_features("P12345")

        assert isinstance(entry, UniProtEntry)
        assert entry.accession == "P12345"
        assert entry.sequence == "MVLSPADKTNVKAAWGKVGAHAGEYGAEAL"
        assert entry.length == 30
        assert entry.protein_name == "Hemoglobin subunit alpha"
        assert entry.gene_name == "HBA1"
        assert entry.organism == "Homo sapiens"
        assert len(entry.features) == 2

    @patch("app.services.sequence.uniprot_service._http_get_json")
    def test_missing_sequence_raises(self, mock_json):
        mock_json.return_value = {"proteinDescription": {}}
        with pytest.raises(UniProtRetrievalError, match="Failed to extract"):
            acquire_uniprot_entry_with_features("P12345")

    @patch("app.services.sequence.uniprot_service._http_get_json")
    def test_invalid_sequence_raises(self, mock_json):
        data = dict(SAMPLE_JSON)
        data["sequence"] = {"value": "12345!!!"}
        mock_json.return_value = data
        with pytest.raises(UniProtRetrievalError, match="Invalid protein sequence"):
            acquire_uniprot_entry_with_features("P12345")

    @patch("app.services.sequence.uniprot_service._http_get_json")
    def test_missing_optional_fields(self, mock_json):
        minimal = {"sequence": {"value": "MVLSPA"}}
        mock_json.return_value = minimal
        entry = acquire_uniprot_entry_with_features("P12345")
        assert entry.protein_name is None
        assert entry.gene_name is None
        assert entry.organism is None
        assert entry.features == ()


# ============================================================================
# Integration-style test (real network — skipped by default)
# ============================================================================


@pytest.mark.skipunless_network
class TestLiveUniprot:
    """
    These tests hit the real UniProt API. Run with:
        pytest -m "skipunless_network" tests/test_uniprot_service.py

    They are skipped by default to keep the test suite fast and offline.
    """

    def test_fasta_live(self):
        seq = acquire_uniprot_protein_fasta("P12345")
        assert len(seq) > 50
        assert AMINO_ACID_PATTERN.match(seq)

    def test_entry_live(self):
        entry = acquire_uniprot_entry_with_features("P12345")
        assert entry.accession == "P12345"
        assert entry.length == len(entry.sequence)
