#!/usr/bin/env bash
# Splits the video into N inclusive frame ranges -> matrix JSON on $GITHUB_OUTPUT.
set -euo pipefail
TOTAL=$(awk -v d="$IN_DUR" -v f="$IN_FPS" 'BEGIN{printf "%d", d*f+0.5}')
N=${IN_CHUNKS:-8}
MAXN=$(( TOTAL / 30 )); [ "$MAXN" -lt 1 ] && MAXN=1   # at least ~30 frames per chunk
[ "$N" -gt "$MAXN" ] && N=$MAXN
[ "$N" -gt 20 ] && N=20
PER=$(( (TOTAL + N - 1) / N ))
ITEMS=()
for ((i=0;i<N;i++)); do
  S=$(( i*PER )); E=$(( (i+1)*PER - 1 )); [ "$E" -ge "$TOTAL" ] && E=$(( TOTAL - 1 ))
  [ "$S" -gt "$E" ] && break
  ITEMS+=("{\"i\":$i,\"range\":\"$S-$E\"}")
done
JSON="[$(IFS=,; echo "${ITEMS[*]}")]"
echo "total=$TOTAL chunks=${#ITEMS[@]} matrix=$JSON"
echo "matrix=$JSON" >> "$GITHUB_OUTPUT"
