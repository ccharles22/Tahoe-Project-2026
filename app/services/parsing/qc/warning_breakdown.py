"""
Categorize QC warnings for a TSV file and print counts + examples.
Run with: PYTHONPATH=. python -m app.services.parsing.qc.warning_breakdown data/parsing/DE_BSU_Pol_Batch_1.tsv
"""
import sys
import collections
import re

from app.services.parsing.tsv_parser import TSVParser
from app.services.parsing.qc import QualityControl


def categorize(warning_text: str) -> str:
    """Map a raw warning string onto a broad warning category."""
    w = warning_text.lower()
    if 'dna' in w or 'dna yield' in w or 'dna_yield' in w:
        return 'dna'
    if 'protein' in w or 'protein_yield' in w:
        return 'protein'
    if 'sequence' in w or 'frameshift' in w or 'invalid characters' in w:
        return 'sequence'
    if 'generation' in w or 'generation 0' in w:
        return 'generation'
    if 'parent' in w or 'orphan' in w:
        return 'parent'
    if 'variant' in w or 'duplicate' in w or 'variant_index' in w:
        return 'variant'
    return 'other'


def main():
    """CLI entrypoint for printing a category breakdown of parsing warnings."""
    if len(sys.argv) < 2:
        print('Usage: app.services.parsing.qc.warning_breakdown <tsv-file> [percentile_low percentile_high dna_floor protein_floor]')
        return

    path = sys.argv[1]
    # optional args
    pct_low = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
    pct_high = float(sys.argv[3]) if len(sys.argv) > 3 else 99.0
    dna_floor = float(sys.argv[4]) if len(sys.argv) > 4 else None
    protein_floor = float(sys.argv[5]) if len(sys.argv) > 5 else None

    parser = TSVParser(path)
    ok = parser.parse()
    if not ok:
        print('Parse errors:')
        for e in parser.errors:
            print(' -', e)
        return

    qc = QualityControl(percentile_mode=True, percentile_low=pct_low, percentile_high=pct_high)
    qc.compute_thresholds_from_records(parser.records)
    # apply absolute floors if provided (override computed thresholds only on lower bound)
    if dna_floor is not None:
        qc.dna_yield_min_warning = min(qc.dna_yield_min_warning or dna_floor, dna_floor)
    if protein_floor is not None:
        qc.protein_yield_min_warning = min(qc.protein_yield_min_warning or protein_floor, protein_floor)
    parser.validate_all(qc)

    counts = collections.Counter()
    examples = collections.defaultdict(list)

    for w in parser.warnings:
        cat = categorize(w)
        counts[cat] += 1
        if len(examples[cat]) < 5:
            examples[cat].append(w)

    print('Total records:', len(parser.records))
    print('Total warnings:', len(parser.warnings))
    print('\nWarning counts by category:')
    for k, v in counts.most_common():
        print(f'  {k}: {v}')

    print('\nExamples (up to 5 per category):')
    for k in counts:
        print(f'\n== {k} ({counts[k]}) ==')
        for ex in examples[k]:
            print(' -', ex)


if __name__ == '__main__':
    main()
