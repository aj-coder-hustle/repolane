#!/usr/bin/env bash
# Usage: copy-repo.sh <source-checkout> <dest-dir>
# Copies the git database only, drops worktree/cursor metadata, checks out the
# default branch fresh. Then copies a whitelist of meaningful ignored files.
set -euo pipefail
src="$1"; dst="$2"
[ -e "$dst/.git" ] && { echo "exists: $dst"; exit 0; }
mkdir -p "$dst"
cp -a "$src/.git" "$dst/.git"
rm -rf "$dst/.git/worktrees" "$dst/.git/index.lock"
cd "$dst"
# origin/HEAD is only set by `git clone`. A checkout whose remote was added by hand has none,
# so fall back to what is checked out, then to the usual names, before giving up.
def=$(git symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##') || def=""
if [ -z "$def" ]; then def=$(git -C "$src" symbolic-ref -q --short HEAD 2>/dev/null) || def=""; fi
if [ -z "$def" ]; then
  for c in main master develop; do
    if git show-ref -q --verify "refs/heads/$c" || git show-ref -q --verify "refs/remotes/origin/$c"; then def=$c; break; fi
  done
fi
[ -n "$def" ] || { echo "cannot tell which branch is the default in $src" >&2; exit 1; }
git checkout -q -f "$def" 2>/dev/null || git checkout -q -f -B "$def" "origin/$def"
git reset -q --hard "origin/$def" 2>/dev/null || true
# meaningful ignored files
# Most repos have none of these, and grep exits 1 when it matches nothing — which under
# `pipefail` would abort the whole copy. Finding nothing is a normal outcome, not a failure.
( cd "$src" && git status --porcelain --ignored -z 2>/dev/null | tr '\0' '\n' | sed -n 's/^!! //p' ) \
 | { grep -E '(^|/)(\.env[^/]*|settings\.local\.json|[^/]*\.code-workspace)$' || true; } \
 | while read -r f; do [ -e "$src/$f" ] || continue; mkdir -p "$(dirname "$f")"; cp -a "$src/$f" "$f"; echo "  copied ignored: $f"; done
echo "copied: $dst on $def  branches=$(git branch | wc -l | tr -d ' ') stashes=$(git stash list | wc -l | tr -d ' ')  src_branches=$(git -C "$src" branch | wc -l | tr -d ' ') src_stashes=$(git -C "$src" stash list | wc -l | tr -d ' ')"
