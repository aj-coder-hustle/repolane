# `registry/` — the source of truth

`repos/` and `lanes/` are machine state: they can be deleted and rebuilt. This folder is the part
that cannot. It is small, it is plain text, and it is the only thing in the control plane that is
committed to git.

| | |
|---|---|
| `config.yml` | who this control plane belongs to, and where ticket keys link |
| `repos.yaml` | every repo under management |
| `lanes/<id>.md` | one file per piece of work — **this is the allow-list for a session** |
| `lanes/done/` | finished lanes, archived rather than deleted |
| `branch-audit.md` | written by `lane audit`; branches with no upstream or unpushed work |
| `old-checkouts.json` | optional: checkouts from before you adopted Repolane, so the guard can refuse them |

## `config.yml`

The one file someone else has to edit to adopt the system. `lane init` writes it.

```yaml
owner:
  name: Sam Okonjo          # named in hook messages: "ask Sam Okonjo first"
tracker:
  url: https://example.atlassian.net/browse/{key}
lanes:
  stale_days: 21                    # lane doctor flags a lane untouched this long; 0 turns it off
  delete_sessions_on_done: false    # default answer to lane done's session-cleanup prompt
protection:
  sync_days: 7                      # lane doctor flags a repo unchecked by lane sync this long; 0 off
```

`{key}` is replaced with the lane's `ticket:` field, or with the key at the front of its id
(`ABC-123-short-name` → `ABC-123`). Leave `url` blank and ticket keys render as plain text.

If `name` is missing or still says `YOUR NAME`, everything falls back to "the user", so a fresh
clone that nobody has configured still reads sensibly.

An advanced, opt-in `shared_rules:` block (`url:`, `pinned_sha:`) is written by `lane rules pull`
— see [`docs/extending.md`](../docs/extending.md). `lane init` never adds it and never asks about
it; a maintainer sets it up deliberately. It feeds `registry/rules.shared.yaml` (gitignored, like
`rules.yaml`) and `registry/.shared-cache/` (also gitignored — the pulled repo's own clone).

## `repos.yaml`

Written by `lane add`. One block per repo:

```yaml
repos:
  web:
    path: repos/web
    origin: https://github.com/your-org/web.git
    default_branch: main
    stack: []
    product: (fill in)
    status: active            # active | archived
    added: 2026-09-18
```

Two optional fields earn their keep:

- **`compare_branch`** overrides `default_branch` when the branch you *merge into* is not the one
  git reports. `origin/HEAD` goes stale — the repo still advertises `master` while the team has
  moved to `develop` — and `lane start` branches from whatever this says.
- **`short`** is an alias you can type instead of the full name. `lane run api …` matches either the
  repo name or its short, case-insensitively, and the board labels repos with it.
- **`old_paths`** records where an adopted checkout came from, which is how `lane import` finds the
  Claude conversations you already had about that repo.
- **`protected_branches`** and **`protection_synced`** are written by `lane sync` — the repo's real
  GitHub branch protection, as of the date given, unioned into the guard's protected-branch check
  alongside `default_branch`/`compare_branch` and the `main`/`master`/`develop` baseline. Never
  written by anything else; `lane doctor` flags a repo where this has gone stale.

`stack` and `product` are yours to fill in; nothing reads them, but a session does.

## `lanes/<id>.md`

One file per piece of work. YAML-ish frontmatter, then four sections. `lane start` creates it and
the scripts maintain it — but it is a text file, and editing it by hand is expected.

```markdown
---
id: ABC-123
status: active            # active | parked | done
ticket:                   # optional; otherwise taken from the front of the id
created: 2026-09-18
updated: 2026-09-18
repos:
  - repo: web
    branch: ABC-123
    base: main
  - repo: api
    branch: ABC-123
    base: main
refs:                     # written by lane-ref
  - path: /Users/sam/specs/billing
    name: billing
    mode: read            # read | rw
    note: the spec this implements
---

## Goal
(one paragraph: what done looks like)

## Resume note
(written by lane-park: where things stand, next step, blockers)

## Findings
(things learned that matter only while this work is live; archived with it)

## Log
- 2026-09-18 started
```

**The `repos:` list is the scope.** The guard reads it to decide what a session may touch, and
`EnterWorktree name="<id>"` resolves through it. A repo that is not in this list does not exist as
far as the session is concerned.

**`## Findings` is the fourth memory scope.** Things that are true only while this work is live go
here and are archived with the lane. `lane done` prints them before archiving and reminds you that
anything still true afterwards belongs in `memory/<repo>/` instead.

**`## Log`** is append-only and partly automatic: `lane park` records the note, and the `SessionEnd`
hook appends a line with each repo's branch, ahead/behind and dirty counts, plus which files were
touched — and flags the lane `UNPARKED` if a session ended with uncommitted work.

## Finishing

`lane done` moves the file to `lanes/done/<id>.md` rather than deleting it, so the history of what
you worked on survives. It runs only after every repo is verified clean and pushed.

## Editing from a session

A lane's own file is editable from inside that lane, and from a dispatcher session at the control
plane root. Another lane's file is not — the guard refuses it, because a session quietly rewriting
the scope of work it is not doing is how the registry stops being true.
