#!/usr/bin/env bash
set -euo pipefail

GEN="${1:-1}"
MODE="${2:-surface}"       # scatter | surface
METHOD="${3:-pca}"         # pca | tsne
GRID="${4:-60}"            # surface resolution (matches pipeline default)
INCLUDE_TSNE="${5:-0}"     # 0 | 1

OUTDIR="outputs"

# If method is tsne, tsne coordinates must be computed
if [[ "${METHOD}" == "tsne" ]]; then
  INCLUDE_TSNE="1"
fi

echo "== Running bonus visualisation pipeline =="
echo "Generation:  ${GEN}"
echo "Mode:        ${MODE}"
echo "Method:      ${METHOD}"
echo "Grid:        ${GRID}"
echo "IncludeTSNE: ${INCLUDE_TSNE}"
echo "Outdir:      ${OUTDIR}"
echo
echo "Outputs:"
echo "  - Activity landscape (all gens)"
echo "  - Domain enrichment heatmap (all gens)"
echo "  - Mutation fingerprint (interactive selector)"
echo "  - Mutation frequency by position"
echo

ARGS=(
  --generation-id "${GEN}"
  --outputs-dir "${OUTDIR}"
  --landscape-mode "${MODE}"
  --landscape-method "${METHOD}"
  --grid-size "${GRID}"
)

if [[ "${INCLUDE_TSNE}" == "1" ]]; then
  ARGS+=( --include-tsne )
fi

# Views already exist in the shared DB (created by the owner).
# Skip CREATE to avoid permission / schema drift issues.
ARGS+=( --skip-create-views )

# Skip REFRESH if your DB role lacks refresh privileges on the MVs.
ARGS+=( --skip-refresh-views )

python -m analysis.pipelines.run_bonus_pipeline "${ARGS[@]}"

echo
echo "Done. Open HTML outputs in: ${OUTDIR}"