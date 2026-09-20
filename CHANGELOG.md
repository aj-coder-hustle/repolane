# Changelog

Notable changes to Repolane. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the version numbers follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

`lane --version` reports the version in [`VERSION`](VERSION), which is the only place the number is
written down. Inside a git checkout it also says how far past the release tag you are.

## [Unreleased]

### Added

- **`scripts/local/<name>`**: any executable file there becomes a `lane <name>` subcommand,
  without ever editing the tracked `lane` dispatcher again. Gitignored, a full peer of built-in
  commands (can `source scripts/lib.sh` itself), listed in `lane help` under "your commands:",
  and flagged by `lane doctor` if a name collides with — and is therefore shadowed by — a real
  built-in. See [`docs/extending.md`](docs/extending.md).
- **`lane rules pull`**: a shared, git-backed source for `registry/rules.yaml`-style rules and
  `scripts/local/` scripts, for a team that wants the same guard rules everywhere. SHA-pinned —
  a plain re-pull re-verifies the pin and refuses to advance past it, `lane rules pull --latest`
  is required to intentionally move; files are always copied, never symlinked, into
  `registry/rules.shared.yaml` (a separate file from `registry/rules.yaml`, never merged into
  it) and `scripts/local/`; rule ids are namespaced to the shared repo. `guard.py`'s
  `load_rules()` now unions every `registry/rules.*.yaml` file through the identical
  parse/validate/deny-only path, so a shared rule is checked exactly like a local one. `lane
  doctor` gets a new, more prominent advisory when the pinned SHA has drifted from the shared
  repo's real HEAD. `lane rules status` inspects the configured source without changing
  anything. See [`docs/extending.md`](docs/extending.md).

## [0.5.0] — 2026-09-20

### Added

- **`lane install` refuses or confirms before repointing an existing symlink**, instead of
  silently repointing it. Running it again — a second checkout, a moved clone — used to relink
  `dest/lane` with zero visibility into what it used to point at. A terminal now shows both paths
  and asks; a non-interactive run (an agent, a script) refuses unless `--force` is passed.
- **`lane doctor` checks three more things, advisory-only like its existing reports**: whether the
  `lane` resolved on `PATH` actually points at this checkout (the exact bug the `lane install` fix
  above surfaces, instead of a confusing downstream symptom), whether `gh` is installed and
  authenticated (`lane sync`/`lane gh` need it), and whether each active lane's spec file
  (`repo:`/`branch:`) still matches what's actually checked out under `lanes/<id>/` on disk.
- **`lane upgrade`** automates the manual procedure documented in Troubleshooting's "Upgrade
  friction" section: refuses if tracked files outside `registry/`, `memory/`, `knowledge/`,
  `CLAUDE.md` and `.claude/settings.local.json` are dirty, fetches, and fast-forwards onto
  upstream only when that's a clean fast-forward — any real divergence or conflict stops with the
  same manual recipe (including the `.claude/settings.json` `git checkout --theirs` step) rather
  than attempting a merge, which this deliberately never does. On success it prints the `VERSION`
  delta and the `CHANGELOG.md` sections that landed, then runs `lane doctor`.

## [0.4.0] — 2026-09-20

### Added

- **`lane doctor` flags repos with undeclared candidate secret/credential files.** `lane secrets
  scan|add|list` already let a repo declare filenames the guard's built-in pattern misses
  (`.npmrc`, `id_rsa`, `service-account.json`, ...), but nothing ever prompted you to actually run
  it — a repo added before the feature existed, or where the prompt was declined, sat with zero
  per-repo protection, silently. `lane doctor` now re-runs the same local, no-network scan every
  time and lists any repo with candidates nobody has declared, with the exact command to fix it —
  same advisory-only philosophy as the stale-lane and branch-protection-sync reports, and simpler
  than both since a local filesystem scan needs no staleness window at all.

## [0.3.0] — 2026-09-20

### Added

- **`lane sync [repo]`** checks a repo's real GitHub branch protection (`gh api
  repos/<owner>/<repo>/branches`) and records it in `registry/repos.yaml` as
  `protected_branches:` + `protection_synced: <date>`. `guard.py`'s protected-branch check now
  unions that list in too, alongside `main`/`master`/`develop` and a repo's own
  `default_branch`/`compare_branch` — never fewer branches protected, only ever more accurate.
  Manual and always available; never run automatically by any other command, so nothing that
  "starts work" blocks on a network call. Fails soft (a clear message, never a crash) for a repo
  that isn't on GitHub, or when `gh` is missing or unauthenticated. `lane doctor` now also lists,
  informationally only, any managed GitHub repo whose protection hasn't been checked in
  `protection: sync_days` (`registry/config.yml`, 7 by default; `0` turns it off).

## [0.2.1] — 2026-09-20

### Fixed

- **The guard's default-branch protection (push, force-push, delete/move) only ever recognised
  `main`/`master`/`develop`, hardcoded.** A repo whose integration branch is named something else —
  `release`, `staging`, anything — got none of that protection, including this repo's own `release`
  branch, added by the release-automation work without updating the guard. `registry/repos.yaml`
  already records each repo's `default_branch`/`compare_branch` (set by `lane add`, used elsewhere
  to resolve a lane's base) but `guard.py` never read it. It now unions that into the protected-branch
  check per repo — never fewer branches protected than before, just more accurate when a repo's own
  integration branch has a different name.

## [0.2.0] — 2026-09-19

### Added

- **`lane add` accepts a local checkout with no `origin` remote.** It used to die outright; it now
  registers the repo as local-only (`origin: (local-only)` in `registry/repos.yaml`) and says so,
  including how to add one later: `git -C repos/<name> remote add origin <url>`.
- **`lane secrets <repo> scan|add|list`.** Every repo can have its own credential filenames beyond
  the built-in `.env`/`.pem`/`credentials.json` set the guard already denies globally. `lane add`
  now scans a newly added repo by filename only (never contents) and either prompts to protect the
  candidates it finds (interactive) or reports them for review (agent-driven, so nothing is added
  without a human confirming). Protecting a file writes deny rules into `registry/rules.yaml`, the
  same mechanism described in [`docs/rules.md`](docs/rules.md#rules-of-your-own), so `lane doctor`
  verifies them the same way it verifies any other custom rule.
- **`lane done` now asks what to do with a finished lane's Claude sessions.** Removing a
  worktree left `~/.claude/projects/<slug>` behind forever, unreported. `lane init` now asks
  (`registry/config.yml`'s `lanes: delete_sessions_on_done:`, default keep) which way the prompt
  defaults, but the prompt itself is never skipped in an interactive run; `lane done <id>
  --delete-sessions`/`--keep-sessions` answer it up front, and a non-interactive run (no
  terminal — an agent driving `lane done`) never deletes, it only reports the count.

### Fixed

- **`lane sessions <repo>` was checking a folder that can never have sessions in it.** It looked
  under the slug for `repos/<repo>` — the mirror — but Claude Code is never launched there (the
  guard refuses `cd`-ing into it). It now unions every live lane worktree for the repo, every
  finished lane's worktree (reconstructed from the archived lane file even though the folder is
  gone), and notes separately how many conversations still sit at the repo's pre-Repolane
  checkout (`old_paths:`), not yet brought in with `lane import`.
- **`pref`-scoped memory was written but never read back into a session.** `lane-memory file <slug>
  pref` correctly appended to `knowledge/preferences.md`, but `memory_brief()` in
  `scripts/hooks/guard.py` never read that file, so the most durable scope — meant to apply to
  every lane, forever — was the one scope that silently never reached a session. It now has its
  own `## preferences` section, read the same way the cross-repo and per-repo sections are.

- **`lane env <repo-name>` silently checked nothing.** `lane-env-check` filtered worktrees by lane
  id only, so `lane env <repo-name>` matched no worktree and printed nothing — a result
  indistinguishable from "all good." It now matches against either the lane id or the repo name.

## [0.1.0] — 2026-09-18

First release. Everything below was built between 2026-09-17 and 2026-09-18; there are no earlier
versions, and this is the first tag. It is early, solo-authored software with no external users yet:
used daily by its author, stable for that use, and unproven anywhere else. The layout on disk and
the command names are settled, and the guard has a real test suite — expect rough edges outside the
paths that get walked every day.

### Added

- **Lanes.** `lane start <id> <repo>…` gives each named repo a worktree on one shared branch under
  `lanes/<id>/`, alongside a spec file in `registry/lanes/`. Repos live once in `repos/` as clean
  mirrors, so a second lane costs a checkout rather than a clone. `lane resume`, `lane park`,
  `lane with`, `lane merge` and `lane done` move work through its life.
- **A permission guard.** `scripts/hooks/guard.py` is a hook dispatcher that fences a Claude Code
  session into the lane it belongs to: it refuses reads of other lanes and of the mirrors, refuses
  `.env` and credential files outright, requires an explicit `ALLOW_DEFAULT_BRANCH_PUSH=1` marker to
  push to a default branch, and routes every memory write through a scope the owner chooses.
  Each refusal is documented in [`docs/rules.md`](docs/rules.md) together with the failure behind it.
- **`lane doctor`.** Compiles the guard, fires nine named probes at it and reports every verdict,
  then checks that every lane, worktree and the control-plane root is still wired to it.
- **`lane board`.** A local, no-build git client scoped to the work in flight.
- **Memory and knowledge.** `lane note` writes what a session learned into `memory/<repo>/` or
  `knowledge/`, under a scope the owner picks rather than one the model picks.
- **Documentation.** A README that explains the problem before the mechanism, plus
  [`docs/concepts.md`](docs/concepts.md), [`docs/rules.md`](docs/rules.md),
  [`docs/commands.md`](docs/commands.md), [`docs/board.md`](docs/board.md), and a README in every
  folder with something non-obvious in it.
- **`CHANGELOG.md` and `VERSION`**, so `lane --version` reports something other than `dev`. It reads
  `VERSION`, which works from a downloaded tarball with no git metadata, and adds the distance from
  the release tag when there is a git checkout to ask.
- **`docs/troubleshooting.md`**: what each failure looks like on disk and how to recover from it.

### Fixed

- **The guard test suite tested nothing on almost every machine.** It was written against a fixture
  only the author had — a lane named `docs` containing a repo named `docs` — and when that was
  missing it printed "Skipped" and exited 0. It was also the evidence behind a public claim of 179
  cases. It now builds its own throwaway control plane under `$HOME`, runs every case against a copy
  of the guard inside it, removes it on exit, and asserts the case count so a run that quietly stops
  testing fails instead of looking like a pass. It touches no real lane, repo or memory file.
- **`lane doctor` reported green on a disarmed control plane.** It checked that the guard compiled
  and refused one probe — not that anything still called it. It now verifies the wiring too, and
  names the lanes and worktrees that have lost it. One unfalsifiable line became nine probes,
  including a control that must come back *undecided*, because a guard that refuses everything
  passes all eight refusal probes and is still useless.
- **A lane could disarm its own guard with a shell redirect.** The control-plane rule was wired into
  `Edit`/`Write` but not into Bash write targets, so `echo '{}' > lanes/<id>/.claude/settings.local.json`
  removed a lane's hooks silently while the file tools refused the same thing. Absolute paths under
  the control plane are now tokenised, `mv` counts both ends, the judgement is shared between the two
  paths so they cannot drift apart again, and a session's own `.claude/settings*` is refused outright.
- **The board staged, committed and pushed secrets.** `is_secret()` gated listing and diffing but not
  `/api/stage`, so a `.env` could be committed through the UI — and because the diff is withheld,
  without anyone seeing what they were committing. Staging a secret is now refused by name, and
  `/api/commit` refuses a staged secret as a second line of defence. Unstaging stays allowed.
- **`lane with` could never succeed.** It exec'd `lane-start`, whose "already has a folder" check
  fires unconditionally, and a started lane always has a folder. Growing a lane now inverts that
  check rather than sharing it.
- **`lane install` put `bin/README.md` on your PATH.** It linked every entry in `bin/`, and the
  printed count was one too high. It now links only executables, and removes such a link left by an
  earlier install — but only when it points into a Repolane `bin/` at something that is not a
  command, so an unrelated file in the same directory is never touched.
- **Drift detection had three readers and no writer.** `registry/old-checkouts.json` was read by
  `status-all`, `session-start` and the guard, and nothing ever created it, so drift was permanently
  empty and the guard never refused the abandoned checkouts it claimed to. `lane add` now records
  the checkout it adopted.
- **The resume note swallowed the findings.** It was read as everything between `## Resume note` and
  `## Log`, but `## Findings` sits between them, so every finding was printed twice. All three
  sections now stop at the next heading of any kind.
- **`lane merge` could mark a repo you were committing to as read-only**, by leaving a stray
  `mode: read` in the repos block. The frontmatter is now rebuilt deterministically instead of being
  rewritten by two overlapping regexes.
- **`lane done` from inside the lane printed three `getcwd` errors** after "removed worktree", which
  reads like data loss. It steps out to the control-plane root first.
- **`lane brief` failed on a finished lane**, though the archive is the point of keeping it. It falls
  back to `registry/lanes/done/`, and an unknown id now lists the lanes that do exist.
- **`lane <cmd> --help` was read as a lane id** and answered `no lane '--help'`. The dispatcher
  answers it now, from the same line `lane help` prints.
- **Commands run before `lane init` crashed** with raw git and Python errors. They now say to run
  `lane init`.
- **`lane env <id>` was documented as taking a repo name.** It filters on lane id, so passing a repo
  name printed nothing at all and looked like a clean result.
- Guard leftovers from the `ws` → `lane` rename: the memory-gate exemption no longer recognised the
  tool's own scripts, and `SessionEnd` rewrote the lane file with BSD-only `sed -i ""`.
- A folder `README.md` was indexed as a cross-repo memory wherever memory files are listed.

### Changed

- **Renamed from Lane to Repolane.** Branding only: the command is still `lane`, as are the `lanes/`
  folder, `registry/lanes/` and every `lane-*` script — the same way Homebrew ships `brew`.
- Two documented claims were corrected rather than fixed, because the code was right and the docs
  were not. A `lane ref` is read-only to a session via the hook, not on disk — it is a symlink. And
  the board fetches its typefaces from Google Fonts, so "no network calls beyond its own server" was
  false; [`docs/board.md`](docs/board.md) now says so, and how to remove them.

[Unreleased]: https://github.com/aj-oss-tools/repolane/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/aj-oss-tools/repolane/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/aj-oss-tools/repolane/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/aj-oss-tools/repolane/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/aj-oss-tools/repolane/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/aj-oss-tools/repolane/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/aj-oss-tools/repolane/releases/tag/v0.1.0
