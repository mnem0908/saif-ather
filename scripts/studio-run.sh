#!/usr/bin/env bash
# Runs SA Motion Studio + a tunnel on this runner, publishes the link to LINK.md,
# and hands over to a fresh run before GitHub's 6h job limit.
set -uo pipefail
: "${GITHUB_REPOSITORY:?}"; : "${GH_TOKEN:?}"
RUN_SECS=${SA_RUN_SECONDS:-21120}            # exit after 5h52m
HANDOVER_SECS=${SA_HANDOVER_SECONDS:-19500}  # start the next run at 5h25m (27 min overlap)
STUDIO_CMD=${STUDIO_CMD:-python3 -u SA_Motion_Studio_v10.py}
TRIES=${SA_STARTUP_TRIES:-450}
REMOTE=${PUBLISH_REMOTE:-https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git}
LOG=studio.log

if [ -z "${SA_KEY:-}" ]; then
  echo "::error::Secret SA_KEY is missing. Run: gh secret set SA_KEY -R ${GITHUB_REPOSITORY}"; exit 1
fi
if [ "${HANDOVER:-false}" != "true" ]; then
  others=$(gh run list -w studio.yml -R "$GITHUB_REPOSITORY" --status in_progress --json databaseId -q "[.[]|select(.databaseId != ${GITHUB_RUN_ID:-0})]|length" 2>/dev/null || echo 0)
  if [ "${others:-0}" -gt 0 ]; then echo "Another studio run is already active; exiting."; exit 0; fi
fi

export SA_HIDE_KEY=1 PYTHONUNBUFFERED=1
START=$(date +%s)
: > "$LOG"
$STUDIO_CMD >> "$LOG" 2>&1 &
PID=$!
tail -n +1 -F "$LOG" 2>/dev/null &
TAILPID=$!
trap 'pkill -P $PID 2>/dev/null; kill $PID $TAILPID 2>/dev/null' EXIT

URL=""
for _ in $(seq 1 "$TRIES"); do            # up to ~15 min for setup (npm, chrome, whisper deps)
  sleep 2
  kill -0 $PID 2>/dev/null || { echo "::error::Studio process exited during startup"; echo "--- last log lines ---"; tail -n 60 "$LOG"; exit 1; }
  if grep -q "جاهز للعمل" "$LOG"; then
    URL=$(grep -m1 -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$LOG" || true); break
  fi
done
if [ -z "$URL" ]; then echo "::error::No tunnel URL was produced"; echo "--- last log lines ---"; tail -n 60 "$LOG"; echo "--- server.log ---"; tail -n 20 server.log 2>/dev/null; echo "--- cloudflared.log ---"; tail -n 20 cloudflared.log 2>/dev/null; exit 1; fi
echo "STUDIO URL: $URL"

publish() {
  local dir; dir=$(mktemp -d)
  git clone -q --depth 1 "$REMOTE" "$dir" || return 1
  cat > "$dir/LINK.md" <<MD
# 🎬 SA Motion Studio

**الرابط الحالي:** $URL

افتحه هكذا (ضع مفتاحك بعد \`?k=\`):

\`$URL/?k=مفتاحك\`

آخر تحديث: $(date -u '+%Y-%m-%d %H:%M UTC') — الرابط يتغيّر كل ~6 ساعات (يُحدَّث هذا الملف تلقائيًا).
MD
  printf '{"url":"%s","updated":"%s"}\n' "$URL" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" > "$dir/link.json"
  ( cd "$dir" && git config user.name "studio-bot" && git config user.email "studio-bot@users.noreply.github.com" \
    && git add LINK.md link.json && { git diff --cached --quiet || git commit -q -m "studio link"; } \
    && { git push -q origin HEAD 2>/dev/null || { git pull -q --rebase origin "$(git rev-parse --abbrev-ref HEAD)" && git push -q origin HEAD; }; } )
  local rc=$?; rm -rf "$dir"; return $rc
}
publish && echo "LINK.md updated" || echo "::warning::could not update LINK.md"

if [ -n "${TG_BOT_TOKEN:-}" ] && [ -n "${TG_CHAT_ID:-}" ]; then
  curl -fsS -m 20 "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" \
    --data-urlencode "chat_id=${TG_CHAT_ID}" --data-urlencode "text=🎬 SA Motion Studio: ${URL}/?k=مفتاحك" >/dev/null || true
fi
{ echo "### 🎬 SA Motion Studio"; echo; echo "$URL"; } >> "${GITHUB_STEP_SUMMARY:-/dev/null}"

HANDED=0
while true; do
  sleep 30
  NOW=$(( $(date +%s) - START ))
  if ! kill -0 $PID 2>/dev/null; then
    echo "::warning::Studio died; starting a replacement run"
    gh workflow run studio.yml -R "$GITHUB_REPOSITORY" -f handover=true || true; exit 1
  fi
  if [ $HANDED -eq 0 ] && [ $NOW -ge $HANDOVER_SECS ]; then
    echo "Starting next run (handover)"; gh workflow run studio.yml -R "$GITHUB_REPOSITORY" -f handover=true || true; HANDED=1
  fi
  [ $NOW -ge $RUN_SECS ] && { echo "Time limit reached; stopping."; exit 0; }
done
