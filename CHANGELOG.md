# Changelog

Notable changes to Repolane. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the version numbers follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

`lane --version` reports the version in [`VERSION`](VERSION), which is the only place the number is
written down. Inside a git checkout it also says how far past the release tag you are.

## [Unreleased]

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

### Fixed

- **`pref`-scoped memory was written but never read back into a session.** `lane-memory file <slug>
  pref` correctly appended to `knowledge/preferences.md`, but `memory_brief()` in
  `scripts/hooks/guard.py` never read that file, so the most durable scope — meant to apply to
  every lane, forever — was the one scope that silently never reached a session. It now has its
  own `## preferences` section, read the same way the cross-repo and per-repo sections are.

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

[Unreleased]: https://github.com/aj-oss-tools/repolane/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/aj-oss-tools/repolane/releases/tag/v0.1.0
