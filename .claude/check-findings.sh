#!/usr/bin/env bash
# Stop hook: a FINDINGS.md that reports a number without reporting its baseline
# is the failure mode that produced finding 06's retracted "8 points of
# legibility" (61% of it turned out to be format leakage). This cannot judge
# whether a control is CORRECT -- only whether one is present at all.
set -u
cd "$(dirname "$0")/.." || exit 0

changed=$(git status --porcelain --untracked-files=all 2>/dev/null | awk '{print $2}' \
          | grep -E '^experiments/.*/FINDINGS\.md$' || true)
[ -z "$changed" ] && exit 0

missing=""
for f in $changed; do
  [ -f "$f" ] || continue
  if ! grep -qiE 'baseline|null|control|chance|by construction|mechanically' "$f"; then
    missing="$missing $f"
  fi
done

[ -z "$missing" ] && exit 0

printf '{"systemMessage":"FINDINGS.md changed with no baseline/null/control mentioned:%s\n\nBefore reporting a number, state what it would be if nothing were happening. See CLAUDE.md and experiments/06_discrete_core/leakage.py."}\n' "$missing"
