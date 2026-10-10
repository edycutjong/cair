#!/bin/bash
# Save `entire graph <args>` output to evidence/entire/<name>.txt with the local repo path replaced by <repo>.
# Usage: scripts/entire_evidence.sh <name> <entire graph args...>
set -u
cd "$(dirname "$0")/.." || exit 1
name=$1; shift
out="evidence/entire/$name.txt"
{
  echo "\$ entire graph $*"
  echo "# $(date -u '+%Y-%m-%dT%H:%M:%SZ') at $(git rev-parse --short HEAD)"
  "${ENTIRE_BIN:-entire}" graph "$@" 2>&1
  echo "# exit=$?"
} | sed -e "s#$(pwd)#<repo>#g" -e "s#$HOME#~#g" > "$out"
echo "$out"
