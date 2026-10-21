#!/usr/bin/env bash
# Studio job (IN_JOB url) -> apply-job.cjs ; otherwise simple template props.
set -euo pipefail
if [ -n "${IN_JOB:-}" ]; then
  curl -fsSL --retry 3 "$IN_JOB" -o job.json
  node scripts/apply-job.cjs job.json
else
  bash scripts/make-props.sh
fi
