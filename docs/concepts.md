# Concepts

Five words carry the whole system.

## The clone is the control plane

This is the foundational fact everything else here builds on, not an upgrade footnote. There is no
server, no daemon, no separately-installed app: the folder you cloned **is** Repolane. Every
script resolves its own root the same way, from `scripts/lib.sh`:

```
AD="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
```

`AD` is wherever this checkout happens to sit on disk — nothing hardcodes a path. That single line
is why `lane` works from a clone anywhere, and it is also why this checkout is not a static copy of
the repository the way most clones are: after `lane init`, `registry/` holds your repos and lanes,
`memory/` and `knowledge/` hold what sessions have learned, and `CLAUDE.md` has your name in it.
`git status` on this checkout is dirty by design — that dirt is your control plane's actual state,
not drift to clean up.

It also means `origin` is a real git remote pointed at a real repo — at first, this public
template. `registry/config.yml` can hold a private tracker URL and `registry/old-checkouts.json`
can hold local filesystem paths, so `lane init` disables the push side of `origin`
(`git remote set-url --push origin DISABLED-set-a-private-remote-first`) whenever it still points
at the public template, so a plain `git push` from inside the control plane can't publish either
of those to it. Point `origin` at your own private repo, then re-enable push yourself:
`git remote set-url --push origin <your-repo>`. `lane doctor` flags it if this was never applied.

Two things follow directly:

- **This checkout is where the plane lives.** There is nothing to "deploy" or "install" beyond
  `lane install` registering this checkout in `~/.local/share/lane/planes.json` (the one piece of
  genuinely machine-global state — a small registry of every checkout you've registered, and
  which one is `active`) and putting `lane` plus the long-form commands on your `PATH`. That
  `lane` is a small, stable dispatcher that is never repointed at one specific checkout again —
  it routes each call to whichever registered plane applies (being physically inside a project's
  directory tree wins outright; `active`, set with `lane use <name>`, is the fallback for running
  from outside any of them). One clone is still one control plane; a machine can now cleanly have
  several registered at once, which is what makes it safe to run `lane install` from a second or
  third project without breaking whichever one you were already using.
- **Upgrading means updating THIS checkout in place**, not replacing it or cloning a fresh one.
  `lane upgrade` (or the manual recipe when it refuses) pulls new code from upstream into the same
  folder that holds your registry, memory and knowledge — see
  ["Upgrade friction"](troubleshooting.md#upgrade-friction-the-clone-is-the-control-plane) in
  Troubleshooting for the actual procedure.

## Repo

A repo you work on. It lives once, at `repos/<name>`, and is a **mirror**: always on its default
branch, never edited, never switched. It exists so every piece of work can share one object store.
Add one with `lane add <git-url>` or `lane add <path-to-a-checkout-you-already-have>`.

**Adopting a checkout you already have** (`lane add <path>`) runs `scripts/copy-repo.sh` under the
hood. What it actually does, verified from the script:

- It **copies** `.git` (`cp -a`), it never moves it — your original checkout is completely
  untouched, on whatever branch it was already on, and stays usable exactly as before.
- **All branches and stashes come along**, since they live in `.git` and the whole directory is
  copied — not just the current branch.
- Only the **default branch is checked out** into the new mirror at `repos/<name>`, freshly reset
  to `origin/<default>` (or the source's own checked-out branch if there is no `origin/HEAD`).
- **Worktrees are dropped, not carried over**: `.git/worktrees` metadata is deleted after the copy,
  since a mirror never has worktrees of its own. Any worktree the original checkout had (including
  one for a branch you were actively using) is not recreated automatically — start a lane for that
  branch with `lane start <id> <repo>:<branch>` to get a worktree for it again.
- A short whitelist of meaningful gitignored files (`.env*`, `settings.local.json`,
  `*.code-workspace`) is copied over too, so local config isn't silently lost.

## Lane

**One piece of work**, which may span several repos. It has an id (a ticket key or a short name), a
branch of that name in each repo it touches, and a folder at `lanes/<id>/` holding a worktree of each.

```
lanes/ABC-123/
  web/     a worktree of repos/web on branch ABC-123
  api/     a worktree of repos/api on branch ABC-123
  refs/    anything you attached for reference
```

You run Claude from `lanes/<id>/`, not from inside a repo. No repo is the main one. Reach any of them
with `git -C <repo>`, `lane run <repo> <cmd>`, or by editing `<repo>/path/to/file` directly.

## Worktree

Git's own feature: a second working directory sharing one repository. It is why a lane costs
a checkout of files rather than a full clone, and why switching work is instant.

## Reference

Code or documents that are not one of your repos but matter to the work. `lane ref <id> add <path>`
makes it readable at `lanes/<id>/refs/<name>` and nowhere else.

A **link** is the lighter case: something that only needs a URL — a design doc, an RFC, a second
issue that is not *the* ticket. `ticket:` in the lane file covers the one tracker key; anything else
goes in an optional `links:` block you write by hand, next to `repos:`:

```yaml
links:
  - label: Promo pricing RFC
    url: https://docs.example.com/rfc/promo-pricing
```

`lane brief` prints them, so they reach the session's opening context, and the board shows them
under Goal & notes. Nothing else reads them — it is a breadcrumb list, not a tracker.

## Memory

What Claude has learned, kept in four scopes chosen by **how long it stays true**:

| scope | means | lives in |
|---|---|---|
| `pref` | how to work with you, always | `knowledge/preferences.md` |
| `cross` | true in every repo | `memory/` |
| `repo` | true for one repo after this work ships | `memory/<repo>/` |
| `lane` | only while this lane is live | the lane file |

Memory is never written directly. `lane note` drafts it and asks you which scope it belongs in.
