# Concepts

Five words carry the whole system.

## Repo

A repo you work on. It lives once, at `repos/<name>`, and is a **mirror**: always on its default
branch, never edited, never switched. It exists so every piece of work can share one object store.
Add one with `lane add <git-url>` or `lane add <path-to-a-checkout-you-already-have>`.

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
