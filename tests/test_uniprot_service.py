from app.services.uniprot_service import _parse_fasta_sequence


def test_parse_fasta_sequence_valid():
    fasta = (
        ">sp|O34996|TEST_PROTEIN Example protein\n"
        "MKTAYIAKQR\n"
        "QISFVKSHFS\n"
    )

    seq = _parse_fasta_sequence(fasta)

    assert seq == "MKTAYIAKQRQISFVKSHFS"


def test_parse_fasta_sequence_invalid_header():
    fasta = "MKTAYIAKQRQISFVKSHFS"

    seq = _parse_fasta_sequence(fasta)

    assert seq == ""


def test_parse_fasta_sequence_empty():
    seq = _parse_fasta_sequence("")

    assert seq == ""
