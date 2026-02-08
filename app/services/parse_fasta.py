def parse_fasta(file_bytes: bytes) -> str:
    if not file_bytes:
        raise ValueError("Empty file.")

    text = file_bytes.decode("utf-8", errors="replace").strip()
    if not text:
        raise ValueError("Empty file.")
    if not text.startswith(">"):
        raise ValueError("FASTA must start with a header line beginning with '>'.")

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if sum(1 for ln in lines if ln.startswith(">")) > 1:
        raise ValueError("Please upload a single-record FASTA.")

    seq = "".join(ln for ln in lines if not ln.startswith(">")).upper()
    if not seq:
        raise ValueError("FASTA sequence is empty.")

    allowed = set("ACGTN")
    bad = sorted({c for c in seq if c not in allowed})
    if bad:
        raise ValueError(f"Invalid characters in sequence: {''.join(bad)}")

    return seq
