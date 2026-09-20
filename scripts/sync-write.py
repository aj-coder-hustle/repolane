#!/usr/bin/env python3
"""sync-write.py <repos.yaml> <repo> <protected-branches, one per line on stdin arg>

Writes (or replaces) `protected_branches:` and `protection_synced:` in a repo's block of
registry/repos.yaml. Called only from lane-sync, after gh has already answered — this script
does no network I/O and trusts nothing it is not given directly as argv.

`protected_branches:` uses the same YAML block-list style as `stack: []` elsewhere in this file
(a block list when non-empty, `[]` when GitHub reports nothing protected — see repo-add's own
python heredoc, which this matches). An empty list is written deliberately, not omitted, so
`lane doctor` can tell "synced, nothing extra protected" apart from "never synced".
"""
import datetime
import re
import sys

path, repo, protected_raw = sys.argv[1], sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else "")
names = [n for n in protected_raw.splitlines() if n.strip()]

text = open(path).read()
m = re.search(r"(?:^|\n)(  " + re.escape(repo) + r":\n(?:    .*\n)*)", text)
if not m:
    sys.exit(f"sync-write: no entry for '{repo}' in {path}")
block = m.group(1)

# Strip any protected_branches:/protection_synced: this block already has — a re-sync replaces
# the previous answer outright, it never accumulates stale branch names next to fresh ones.
block = re.sub(r"    protected_branches:( \[\]\n|\n(?:      - .*\n)*)", "", block)
block = re.sub(r"    protection_synced: .*\n", "", block)

if names:
    addition = "    protected_branches:\n" + "".join(f"      - {n}\n" for n in names)
else:
    addition = "    protected_branches: []\n"
addition += f"    protection_synced: {datetime.date.today()}\n"

new_block = block.rstrip("\n") + "\n" + addition
text = text[: m.start(1)] + new_block + text[m.end(1) :]
open(path, "w").write(text)
