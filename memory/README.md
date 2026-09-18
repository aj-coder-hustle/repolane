# `memory/` — what Claude has learned

Two folders hold everything a session is told about *you*, rather than about the code: this one and
[`../knowledge/`](../knowledge/README.md).

```
memory/
  MEMORY.md          the cross-repo index — one line per memory
  <slug>.md          a cross-repo memory: true in every repo, forever
  <repo>/
    MEMORY.md        that repo's index
    <slug>.md        true in that repo, still true after this ticket ships
```

Each repo's folder is symlinked into `~/.claude/projects/<repo-slug>/memory`, so Claude's own memory
directory for that repo *is* this folder — versioned here, with the rest of the control plane,
instead of scattered through your home directory.

## The four scopes

The whole point of this folder is that a memory has to earn its lifetime. Scope is chosen by one
question: **how long does it stay true?**

| scope | means | lives in |
|---|---|---|
| `pref` | how to work with you, in all work forever | `knowledge/preferences.md` |
| `cross` | true in every repo | `memory/<slug>.md` |
| `repo` | true in one repo, after this ticket ships | `memory/<repo>/<slug>.md` |
| `lane` | only while this piece of work is live | the lane's `## Findings`, archived with it |

The survival test, in order: does it stay true after this ticket ships? After you leave this repo?
In work that has nothing to do with this repo? The first "no" names the scope.

## Nothing is written directly

The guard refuses writes to this folder. Creating a memory always goes through `lane note`
(`lane-memory`), in three steps:

```sh
lane-memory draft <slug>                       # prints a path in .cache/memory-inbox/
                                               # Claude writes the draft there
                                               # then asks you which scope, with a recommendation
lane-memory file <slug> repo web               # files it and writes the index line
lane-memory file <slug> cross | pref | lane
```

This exists because the default outcome is otherwise predictable: everything becomes a permanent
global preference, and within a month the system is full of things that were true once. Making the
scope a question someone has to answer is the only thing that reliably prevents it.

Editing a memory that *already* exists is allowed — but only from a dispatcher session at the
control plane root, where its scope is already settled and you are in the conversation. A session
inside a lane is always refused.

## A memory file

```markdown
---
name: migrations-run-before-deploy
description: Schema migrations run in a separate job before the deploy, not on boot.
metadata:
  type: project        # project | feedback | user | reference
---

The deploy pipeline runs `db:migrate` as its own step and fails the deploy if it fails.

**Why:** running them on boot meant a slow migration tripped the health check and rolled the
release back half-applied.
**How to apply:** never add migration calls to application startup.
```

`description` is what lands in the index and what a session sees first, so it should say the fact,
not the topic.

## The index

`MEMORY.md` in each folder is one line per memory, rebuilt from the files themselves:

```sh
lane-memory index          # or: index cross | index repo
```

Indexes are what a session is given at the start of a lane — not the memories themselves. Claude
opens the files whose index line looks relevant, which is what keeps a large memory folder from
eating the context window.

## Keeping it honest

| | |
|---|---|
| `lane-memory audit` | memories filed under one repo that read like they apply everywhere |
| `lane-memory move <name> cross\|repo <repo>` | re-scope one, reindexing both sides |
| `lane-memory rm <name>` | delete it and its index line |
| `lane board` → Memory | browse all four scopes, with duplicate detection |

`README.md` and `MEMORY.md` are skipped by every listing, so this file is not mistaken for a memory.
