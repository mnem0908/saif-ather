#!/data/data/com.termux/files/usr/bin/bash
# One-time setup from Termux: creates a PUBLIC GitHub repo and pushes this project.
# Usage:  bash termux-setup.sh motion-render
set -e
REPO="${1:-motion-render}"
pkg update -y && pkg install -y git gh nodejs
git config --global user.name  >/dev/null 2>&1 || git config --global user.name  "SA Motion"
git config --global user.email >/dev/null 2>&1 || git config --global user.email "sa-motion@users.noreply.github.com"
if ! gh auth status >/dev/null 2>&1; then
  gh auth login --web --git-protocol https --scopes workflow,repo
fi
[ -d .git ] || git init -b main
git add -A
git commit -m "SA Motion Studio: Remotion + parallel GitHub Actions render" || true
gh repo create "$REPO" --public --source=. --remote=origin --push
echo "Done. Open: $(gh repo view --json url -q .url)/actions"
