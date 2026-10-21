#!/usr/bin/env bash
# Builds props.json from env vars set by the workflow.
set -euo pipefail
jq -n --arg mediaUrl "${IN_MEDIA:-}" --arg title "${IN_TITLE:-SA Motion Studio}" --arg template "${IN_TEMPLATE:-title}" --arg mediaType "${IN_MTYPE:-}" \
  --argjson duration "${IN_DUR:-10}" --argjson width "${IN_W:-1080}" --argjson height "${IN_H:-1920}" --argjson fps "${IN_FPS:-30}" \
  --argjson segments "${IN_SEG:-[]}" \
  '{mediaUrl:$mediaUrl,title:$title,template:$template,mediaType:$mediaType,duration:$duration,width:$width,height:$height,fps:$fps,segments:$segments}' > props.json
