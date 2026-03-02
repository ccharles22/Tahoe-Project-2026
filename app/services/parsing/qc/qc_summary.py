"""
Quick QC summary helper — prints warning counts and yield statistics.
Run with: PYTHONPATH=. python -m app.services.parsing.qc.qc_summary
"""
import re
from collections import Counter

try:
    import numpy as np
except Exception:
    np = None

from app.services.parsing.tsv_parser import TSVParser
from app.services.parsing.qc import QualityControl


def show_stats(name, arr):
    """Print a compact percentile summary for a numeric QC series."""
    arr = np.array(arr)
    if arr.size == 0:
        print(f"{name}: no values")
        return
    print(f"\n{name} stats (n={arr.size}):")
    print(f"  min {arr.min():.2f}, 1% {np.percentile(arr,1):.2f}, 5% {np.percentile(arr,5):.2f},"
          f" 25% {np.percentile(arr,25):.2f}, median {np.median(arr):.2f}, 75% {np.percentile(arr,75):.2f},"
          f" 95% {np.percentile(arr,95):.2f}, max {arr.max():.2f}")


def main():
    """CLI entrypoint for summarising TSV parsing QC distributions."""
    parser = TSVParser("data/parsing/DE_BSU_Pol_Batch_1.tsv")
    ok = parser.parse()
    if not ok:
        print("Failed to parse TSV. Errors:")
        for e in parser.errors:
            print(" -", e)
        return

    # Enable percentile-mode so thresholds are computed from this dataset
    qc = QualityControl(percentile_mode=True, percentile_low=1.0, percentile_high=99.0)

    # Compute and show thresholds derived from the dataset, then run validation
    qc.compute_thresholds_from_records(parser.records)
    print("Computed thresholds:")
    print(f"  dna_yield_min_warning: {qc.dna_yield_min_warning}")
    print(f"  dna_yield_max_warning: {qc.dna_yield_max_warning}")
    print(f"  protein_yield_min_warning: {qc.protein_yield_min_warning}")
    print(f"  protein_yield_max_warning: {qc.protein_yield_max_warning}\n")

    parser.validate_all(qc)

    print(f"Total records: {len(parser.records)}")
    print(f"Total errors: {len(parser.errors)}")
    print(f"Total warnings: {len(parser.warnings)}\n")

    counts = Counter()
    for w in parser.warnings:
        key = re.split(r":", w, maxsplit=1)[0]
        counts[key] += 1

    print("Warning counts by prefix:")
    for k, v in counts.most_common():
        print(f"  {k}: {v}")

    dna_vals = []
    prot_vals = []
    for r in parser.records:
        try:
            v = r.get('dna_yield')
            if v not in (None, '', 'NULL'):
                dna_vals.append(float(v))
        except Exception:
            pass
        try:
            v = r.get('protein_yield')
            if v not in (None, '', 'NULL'):
                prot_vals.append(float(v))
        except Exception:
            pass

    if np is None:
        print('\nNumPy not available in this environment; skipping numeric summaries.')
    else:
        show_stats('dna_yield', dna_vals)
        show_stats('protein_yield', prot_vals)


if __name__ == '__main__':
    main()
