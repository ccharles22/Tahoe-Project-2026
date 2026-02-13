"""
UniProt Service functions.

The purpose of these functions are to obtain reference protein sequences from UniProt
using a UniProt accession identifier.

"""

from __future__ import annotations

import re
from typing import Final

import requests

# UniProt REST endpoint for FASTA retrival
UNIPROT_FASTA_URL: Final[str] = "https://rest.uniprot.org/uniprotkb/{accession}.fasta"

# Simple amino-acid alphabet for validation (includes X for unknown amino-acids) 
AMINO_ACID_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^[ACDEFGHIKLMNPQRSTVWYXBZJUO\*]+$"
)

class UniProtRetrievalError(Exception):
    """
   Triggered when a UniProt entry cannot be retrieved or parsed.
    """

def acquire_uniprot_protein_fasta(accession: str, timeout: int = 10) -> str:
    """
    Retrieve the protein sequence for a UniProt accession.

    Parameters:
    accession : str
        UniProt accession identifier (e.g. 'O34996').
    timeout : int
        Timeout (seconds) for the HTTP request.

    Returns:
    str 
        Protein sequence as a single uppercase amino-acid string.

    Raises:
    UniProtRetrievalError
        If the accession is invalid, the request fails or the FASTA content 
        cannot be parsed.
    """
    accession = accession.strip()
    if not accession:
        raise UniProtRetrievalError("UniProt accession must be a non-empty string.")

    url = UNIPROT_FASTA_URL.format(accession=accession)

    headers = {
        # Establishes the client for reliablity and best practice
        "User-Agent": "Tahoe-Project-2026/1.0 (MSc Bioinformatics Group Project)",
        # UniProt supports content negotiation; request FASTA explicitly
        "Accept": "text/x-fasta",
    }

    try:
        response = requests.get(url, headers=headers, timeout=timeout)
    except requests.RequestException as exc:
        raise UniProtRetrievalError(
            f"Network error while retrieving UniProt accession '{accession}'."
        ) from exc

    # Deals with common UniProt API outcomes explicitly for clearer feedback
    if response.status_code == 404:
        raise UniProtRetrievalError(
            f"UniProt accession '{accession}' not found (HTTP 404)."
        )
    
    if response.status_code == 429:
        raise UniProtRetrievalError(
            f"UniProt rate limit reached (HTTP 429). Please retry after 10-15 minutes."
        )
    if 500 <= response.status_code <= 599:
        raise UniProtRetrievalError(
            f"Unexpected UniProt response for '{accession}' (HTTP {response.status}). Try again later."
        )
    if response.status_code != 200:
        raise UniProtRetrievalError(
            f"Failed to parse a protein from UniProt FASTA for '{accession}'."
        )
    

    protein_sequence = _parse_fasta_sequence(response.text)

    if not protein_sequence:
        raise UniProtRetrievalError(
            f"Failed to parse a protein sequence from UniProt FASTA for'{accession}'."
        )
    return protein_sequence

def _parse_fasta_sequence(fasta_text: str) -> str:
    """
    Parse a FASTA-formatted text and returns only the sequence.

    Args:
        fasta_text :  Raw FASTA text returned by UniProt. 

    Returns:
        Concatenated sequence string (uppercase), or "" if invalid.
    """
    if not fasta_text:
        return ""

    lines = [ln.strip() for ln in fasta_text.strip().splitlines() if ln.strip()]
    if not lines or not lines[0].startswith(">"):
        return ""
    
    # Join all sequence lines and normalise
    sequence = "".join(lines[1:]).replace(" ", "").upper()

    # small checks to identify whether the sequence contains letters and valid AA characters
    if not sequence:
        return ""
    
    # UniProt sequences should not contain digits
    if not AMINO_ACID_PATTERN.match(sequence):
        return ""

    return sequence
