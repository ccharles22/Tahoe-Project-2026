"""FASTA parsing and validation for plasmid uploads."""

from __future__ import annotations

_ALLOWED_DNA = set('ACGTN')


def parse_fasta(file_bytes: bytes) -> str:
    """Parse a single-record FASTA upload and return uppercase DNA sequence.

    Raises:
        ValueError: For empty payloads, invalid FASTA shape, or invalid bases.
    """
    if not file_bytes:
        raise ValueError('Empty file.')

    text = file_bytes.decode('utf-8', errors='replace').strip()
    if not text:
        raise ValueError('Empty file.')
    if not text.startswith('>'):
        raise ValueError("FASTA must start with a header line beginning with '>'.")

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if sum(1 for line in lines if line.startswith('>')) > 1:
        raise ValueError('Please upload a single-record FASTA.')

    seq = ''.join(line for line in lines if not line.startswith('>')).upper()
    if not seq:
        raise ValueError('FASTA sequence is empty.')

    bad = sorted({c for c in seq if c not in _ALLOWED_DNA})
    if bad:
        raise ValueError(f"Invalid characters in sequence: {''.join(bad)}")

    return seq
