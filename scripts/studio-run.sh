#!/usr/bin/env bash
# Self-healing supervisor for SA Motion Studio on a GitHub runner.
#  - runs the studio, restarts it if it dies or stops answering
#  - owns the Cloudflare tunnel, restarts it (new URL) if it breaks, republishes the link
#  - hands over to a fresh run before the 6h limit and only retires once the successor is live
set -uo pipefail
REPO=${GITHUB_REPOSITORY:?}; : "${GH_TOKEN:?}"
RUN_ID=${GITHUB_RUN_ID:-0}
RUN_SECS=${SA_RUN_SECONDS:-21300}              # hard stop 5h55m (job limit is 6h)
HANDOVER_SECS=${SA_HANDOVER_SECONDS:-19200}    # start the successor at 5h20m
GRACE_SECS=${SA_GRACE_SECONDS:-420}            # keep serving 7 min after the successor is published
MON=${SA_MON_INTERVAL:-20}
PORT=${SA_PORT:-3847}
STUDIO_CMD=${STUDIO_CMD:-python3 -u SA_Motion_Studio_v10.py}
CF=${CF_BIN:-./cf-bin}
REMOTE=${PUBLISH_REMOTE:-https://x-access-token:${GH_TOKEN}@github.com/${REPO}.git}
LOG=studio.log; TLOG=tunnel.log
START=$(date +%s)
say() { echo "[$(date -u +%H:%M:%S)] $*"; }

if [ -z "${SA_KEY:-}" ]; then echo "::error::Secret SA_KEY is missing. Run: gh secret set SA_KEY -R ${REPO}"; exit 1; fi

active_runs() { gh run list -w studio.yml -R "$REPO" --json databaseId,status 2>/dev/null; }
# a plain start must not duplicate an older active run (ties: the older id wins)
if [ "${HANDOVER:-false}" != "true" ]; then
  older=$(active_runs | jq "[.[]|select(.databaseId < $RUN_ID and (.status==\"in_progress\" or .status==\"queued\" or .status==\"pending\" or .status==\"waiting\"))]|length" 2>/dev/null || echo 0)
  if [ "${older:-0}" -gt 0 ]; then say "An older studio run is active; exiting."; exit 0; fi
fi

export SA_HIDE_KEY=1 PYTHONUNBUFFERED=1 SA_NO_TUNNEL=1
SPID=""; TPID=""; URL=""; RETIRED=0; SUCC_AT=0; LAST_DISPATCH=-100000; RESTARTS=0
: > "$LOG"; : > "$TLOG"

TAILPID=""
cleanup() { [ -n "$TPID" ] && kill "$TPID" 2>/dev/null; [ -n "$SPID" ] && { pkill -P "$SPID" 2>/dev/null; kill "$SPID" 2>/dev/null; }; [ -n "$TAILPID" ] && kill "$TAILPID" 2>/dev/null; return 0; }
trap cleanup EXIT
trap 'exit 0' TERM INT

local_ok()  { curl -fsS -m 5 "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; }
public_ok() { curl -fsS -m 10 "${SA_PUBLIC_CHECK_BASE:-$1}/icon.svg" >/dev/null 2>&1; }

start_studio() {
  [ -n "$SPID" ] && { pkill -P "$SPID" 2>/dev/null; kill "$SPID" 2>/dev/null; sleep 1; }
  $STUDIO_CMD >> "$LOG" 2>&1 &
  SPID=$!
}
wait_local() {  # $1 = tries of 2s
  for _ in $(seq 1 "$1"); do
    kill -0 "$SPID" 2>/dev/null || return 1
    local_ok && return 0
    sleep 2
  done
  return 1
}

ensure_cf() {
  [ -x "$CF" ] && return 0
  for i in 1 2 3 4; do
    curl -fsSL -m 120 -o "$CF" https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 && chmod +x "$CF" && return 0
    sleep $((i*3))
  done
  return 1
}

start_tunnel() {
  [ -n "$TPID" ] && kill "$TPID" 2>/dev/null
  for proto in http2 quic http2; do
    : > "$TLOG"
    "$CF" tunnel --no-autoupdate --protocol "$proto" --edge-ip-version 4 --url "http://127.0.0.1:$PORT" >> "$TLOG" 2>&1 &
    TPID=$!
    for _ in $(seq 1 45); do
      sleep 1
      kill -0 "$TPID" 2>/dev/null || break
      u=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' "$TLOG" | grep -v -E '^https://(api|www|dash|developers|support)\.' | head -1)
      if [ -n "$u" ] && grep -qiE 'registered tunnel connection|Connection [0-9a-f-]+ registered' "$TLOG"; then
        for __ in $(seq 1 20); do public_ok "$u" && { URL="$u"; return 0; }; sleep 2; done
        break
      fi
    done
    kill "$TPID" 2>/dev/null
  done
  return 1
}

read_link() {
  if [ -n "${LINK_READ_CMD:-}" ]; then eval "$LINK_READ_CMD" 2>/dev/null
  else gh api "repos/${REPO}/contents/link.json" -q .content 2>/dev/null | base64 -d 2>/dev/null; fi
}

publish_once() {
  local dir; dir=$(mktemp -d)
  git clone -q --depth 1 "$REMOTE" "$dir" 2>/dev/null || { rm -rf "$dir"; return 1; }
  printf '{"url":"%s","run":"%s","updated":"%s"}\n' "$URL" "$RUN_ID" "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" > "$dir/link.json"
  cat > "$dir/LINK.md" <<MD
# 🎬 SA Motion Studio

الرابط الدائم: **https://${REPO%%/*}.github.io/${REPO##*/}/** (افتحه مرة بـ \`#مفتاحك\` في آخره ثم احفظه)

الرابط الحالي المباشر: $URL

آخر تحديث: $(date -u '+%Y-%m-%d %H:%M UTC') — تشغيل رقم $RUN_ID
MD
  ( cd "$dir" && git config user.name "studio-bot" && git config user.email "studio-bot@users.noreply.github.com" \
    && git add LINK.md link.json && { git diff --cached --quiet || git commit -q -m "studio link"; } \
    && { git push -q origin HEAD 2>/dev/null || { git pull -q --rebase origin "$(git rev-parse --abbrev-ref HEAD)" && git push -q origin HEAD; }; } )
  local rc=$?; rm -rf "$dir"; return $rc
}
publish() {
  for i in 1 2 3 4 5; do publish_once && { say "link published: $URL"; return 0; }; sleep $((i*4)); done
  say "::warning::could not publish link"; return 1
}

dump_logs() { echo "--- studio.log ---"; tail -n 60 "$LOG"; echo "--- tunnel.log ---"; tail -n 20 "$TLOG"; }

# ---------- startup ----------
tail -n +1 -F "$LOG" 2>/dev/null & TAILPID=$!
start_studio
if ! wait_local 600; then echo "::error::Studio did not become healthy"; dump_logs; exit 1; fi
say "studio healthy on :$PORT"
ensure_cf || { echo "::error::could not get cloudflared"; exit 1; }
OKT=0
for round in 1 2 3 4 5; do start_tunnel && { OKT=1; break; }; say "tunnel attempt $round failed"; sleep 5; done
[ $OKT -eq 1 ] || { echo "::error::No tunnel URL was produced"; dump_logs; exit 1; }
say "STUDIO URL: $URL"
publish
{ echo "### 🎬 SA Motion Studio"; echo; echo "$URL"; } >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
if [ -n "${TG_BOT_TOKEN:-}" ] && [ -n "${TG_CHAT_ID:-}" ]; then
  curl -fsS -m 20 "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendMessage" --data-urlencode "chat_id=${TG_CHAT_ID}" --data-urlencode "text=🎬 SA Motion Studio: ${URL}" >/dev/null || true
fi

# ---------- monitor loop ----------
LFAIL=0; PFAIL=0; BEAT=0
while true; do
  sleep "$MON"
  NOW=$(( $(date +%s) - START ))

  # 1) studio health (restart in place; give up to a fresh run after too many restarts)
  if kill -0 "$SPID" 2>/dev/null && local_ok; then LFAIL=0; else LFAIL=$((LFAIL+1)); fi
  if [ $LFAIL -ge 3 ] || ! kill -0 "$SPID" 2>/dev/null; then
    RESTARTS=$((RESTARTS+1)); say "studio unhealthy -> restart #$RESTARTS"
    if [ $RESTARTS -gt 6 ]; then
      say "::warning::too many restarts; requesting a fresh run"; gh workflow run studio.yml -R "$REPO" -f handover=true || true; exit 1
    fi
    start_studio; wait_local 240 && say "studio back" || say "studio still down"; LFAIL=0
  fi

  # 2) tunnel health (new URL + republish unless we are already retired)
  if kill -0 "$TPID" 2>/dev/null && public_ok "$URL"; then PFAIL=0; else PFAIL=$((PFAIL+1)); fi
  if [ $PFAIL -ge 3 ] || ! kill -0 "$TPID" 2>/dev/null; then
    say "tunnel unhealthy -> restarting"
    if start_tunnel; then say "new tunnel: $URL"; [ $RETIRED -eq 0 ] && publish; else say "::warning::tunnel restart failed"; fi
    PFAIL=0
  fi

  # 3) handover: start a successor, wait until it has published, then keep serving a grace period
  if [ $NOW -ge $HANDOVER_SECS ] && [ $RETIRED -eq 0 ]; then
    cur=$(read_link | jq -r '.run // empty' 2>/dev/null || true)
    if [ -n "$cur" ] && [ "$cur" != "$RUN_ID" ]; then
      say "successor run $cur is live; retiring after grace"; RETIRED=1; SUCC_AT=$NOW
    else
      succ=$(active_runs | jq "[.[]|select(.databaseId > $RUN_ID and (.status==\"in_progress\" or .status==\"queued\" or .status==\"pending\" or .status==\"waiting\"))]|length" 2>/dev/null || echo 0)
      if [ "${succ:-0}" -eq 0 ] && [ $((NOW - LAST_DISPATCH)) -ge 180 ]; then
        say "dispatching successor"; gh workflow run studio.yml -R "$REPO" -f handover=true || say "::warning::dispatch failed (will retry)"
        LAST_DISPATCH=$NOW
      fi
    fi
  fi
  if [ $RETIRED -eq 1 ] && [ $((NOW - SUCC_AT)) -ge "$GRACE_SECS" ]; then say "grace period over; stopping"; exit 0; fi
  if [ $NOW -ge $RUN_SECS ]; then say "hard time limit; stopping"; exit 0; fi

  BEAT=$((BEAT+MON)); [ $BEAT -ge 600 ] && { say "heartbeat: uptime ${NOW}s url=$URL restarts=$RESTARTS"; BEAT=0; }
done
