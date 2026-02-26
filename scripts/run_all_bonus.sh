#!/usr/bin/env bash
set -euo pipefail

GEN="${1:-1}"
MODE="${2:-surface}"       # scatter | surface
METHOD="${3:-pca}"         # pca | tsne
GRID="${4:-70}"            # surface resolution
TOPN="${5:-5}"             # trajectory top N
INCLUDE_TSNE="${6:-0}"     # 0 | 1

OUTDIR="outputs/gen_${GEN}"

# If method is tsne, tsne coordinates must be computed
if [[ "${METHOD}" == "tsne" ]]; then
  INCLUDE_TSNE="1"
fi

echo "== Running bonus visualisation pipeline =="
echo "Generation:  ${GEN}"
echo "Mode:        ${MODE}"
echo "Method:      ${METHOD}"
echo "Grid:        ${GRID}"
echo "TopN:        ${TOPN}"
echo "IncludeTSNE: ${INCLUDE_TSNE}"
echo "Outdir:      ${OUTDIR}"
echo

ARGS=(
  --generation-id "${GEN}"
  --outputs-dir "${OUTDIR}"
  --landscape-mode "${MODE}"
  --landscape-method "${METHOD}"
  --grid-size "${GRID}"
  --top-n "${TOPN}"
)

if [[ "${INCLUDE_TSNE}" == "1" ]]; then
  ARGS+=( --include-tsne )
fi

# Skip view creation if MVs already exist:
# ARGS+=( --skip-create-views )

python -m app.services.analysis.bonus.pipelines.run_bonus_pipeline "${ARGS[@]}"

echo
echo "Done. Open HTML outputs in: ${OUTDIR}"