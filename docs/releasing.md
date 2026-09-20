# How releases work

You don't need to read this to fix a bug or add something small — [`CONTRIBUTING.md`](../CONTRIBUTING.md)
covers what a normal pull request needs. This page is the full picture, for anyone who wants to
understand (or debug) the pipeline itself.

## The branch model

```
feature/your-fix ──┐
feature/other      ──┼──PR──►  release   (the staging branch — no PR review required to land
another contributor─┘                     here, but it's protected against force-push/delete)
                                   │
                     push to release with real content under
                     ## [Unreleased] in CHANGELOG.md triggers:
                                   │
                                   ▼
                     .github/workflows/release-plan.yml
                       - reads which ### headings are under Unreleased
                         (### Removed / BREAKING → major
                          ### Added               → minor
                          otherwise (Fixed/Changed/...) → patch)
                       - moves Unreleased's content into a new
                         "## [x.y.z] — <date>" section
                       - regenerates every changelog reference link
                       - bumps VERSION
                       - commits that to release
                       - opens/updates a "Release vX.Y.Z" PR: release → main
                                   │
                     merging that PR is the release action
                                   │
                                   ▼
                                 main   (protected: PR required, CI required —
                                          see that PR's own page for who can merge it)
                                   │
                     merging triggers .github/workflows/tag-release.yml
                     (tags the merge commit vX.Y.Z) and notify-site.yml
                     (rebuilds repolane.dev's changelog page)
```

## Who does what

- **Anyone** (fork or branch, doesn't matter) — fix something, branch from `release`, open a PR
  *into* `release`. That's the entire contribution flow; you never touch `main` directly, and you
  never need to think about version numbers.
- **`release`** is where work lands before it ships. It's not reviewed as strictly as `main` — no
  required approving review, no required status check gating the merge itself — but it's still
  protected against force-push and deletion, and every PR into it still runs the guard's test
  suite (`.github/workflows/test.yml`) so you get fast feedback either way.
- A plain contributor's PR into `release` never becomes a release by itself: it waits there until
  the auto-opened "Release vX.Y.Z" PR (into `main`) gets merged. Nothing about the automation
  decides *when* to ship — only *what version number* the next release should be, once it's
  merged. Who's able to merge it is whatever `main`'s PR page already shows you.

## What you actually need to do in a PR

1. Branch from `release`.
2. Make the change. Run `bash scripts/hooks/test-guard.sh` (and `lane doctor` if you have a clone
   set up).
3. If the change is user-visible, add an entry under `## [Unreleased]` in
   [`CHANGELOG.md`](../CHANGELOG.md), under the right heading (`### Added` for a new capability,
   `### Fixed` for a bug fix, `### Changed`/`### Removed`/`### Security` as they apply) — **this
   heading is what decides the next version's major/minor/patch bump**, so get it right; see the
   diagram above. There's no separate "PR type" field or commit-message convention to learn — the
   changelog entry you'd write anyway is the only input the automation uses.
4. Open the PR against `release`, not `main`.

That's genuinely the whole contributor-facing surface. Everything past step 4 — the version
number, the PR into `main`, the tag, the site rebuild — happens without you, and without the
maintainer needing to do anything by hand either, once they decide to merge.

## Why the changelog entry isn't auto-generated

It would be possible to have CI draft a changelog entry from a PR's title/description
automatically. Deliberately not done, for two reasons: the heading you choose directly decides
the version bump, so an unreviewed, auto-generated entry could silently mis-tag a feature as a
patch (or vice versa); and the entries in this changelog are written with the actual root cause
in mind, not just a summary of the diff — something a PR description alone usually can't give you
as precisely. Writing the entry is the one place in this whole pipeline where a human judgment
call is genuinely load-bearing, so it stays manual on purpose.

## If something in the pipeline itself breaks

The pipeline has needed a couple of fixes to itself along the way (a token permission the
default `GITHUB_TOKEN` doesn't have because the org blocks Actions from opening PRs — see
`RELEASE_PR_TOKEN` in `.github/workflows/release-plan.yml`'s comments; a missing git identity
before tagging in `tag-release.yml`). A fix to the pipeline's own workflow files is not usually
"user-visible" in the `CHANGELOG.md` sense, so it has no changelog entry and `release-plan.yml`
won't open a PR for it on its own — a maintainer currently has to open that PR by hand
(`gh pr create --base main --head release`). This is a known gap, not a bug you need to work
around in a normal contribution.
