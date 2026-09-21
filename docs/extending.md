# Extending Repolane

Two ways to add to a control plane without forking it: your own `lane` subcommands, and (see
below) a shared, git-backed source of `registry/rules.yaml`-style rules for a team.

## Your own `lane <name>` commands

Any executable file in `scripts/local/` becomes a `lane <name>` command, where `<name>` is the
file's own name. Nothing else has to change — not `lane` itself, not any tracked file.

```sh
cat > scripts/local/hello <<'EOF'
#!/usr/bin/env bash
# lane: say hello
echo "hello from scripts/local/hello"
EOF
chmod +x scripts/local/hello
lane hello
```

- `scripts/local/` is gitignored — machine-local, never shipped, never reviewed as part of this
  repo. It is exactly the kind of place a personal shortcut or a company-specific script belongs.
- The second line of the file, if it starts with `# lane: `, is the one-liner `lane help` shows
  next to it — the same convention `lane <cmd> --help` already reads its own usage block from.
- A local script is a full peer of a built-in command: it can `source "$AD/scripts/lib.sh"`
  itself, exactly the way `scripts/repo-secrets` and `scripts/lane-sync` do, and gets the same
  `$AD`/`$S` conventions, `die`, `repo_exists`, and everything else in that library.
- **Built-ins always win.** If `scripts/local/` has a file with the same name as a real `lane`
  command, the built-in runs and the local file never does. `lane doctor` flags this — "shadowed
  by the built-in `<name>` command and will never run" — so it is never a silent surprise.
- **The command name is never a path.** `lane <name>` only ever looks up a bare filename directly
  inside `scripts/local/` — a name containing `/` (path traversal, or reaching some other
  executable entirely) is rejected before the lookup happens, not resolved.
- **The `# lane: ` one-liner is untrusted display text**, not just local shorthand: it can arrive
  from a shared repo's `scripts.d/` via `lane rules pull` (below), landing on every teammate's
  machine with its comment intact. `lane help` strips control/escape characters from it and caps
  it at 72 characters before printing, so it can't clear the screen, recolor the terminal, or
  otherwise do anything beyond show a one-line description.

## Shared, git-backed rules: `lane rules pull`

`registry/rules.yaml` (see [`docs/rules.md`](rules.md#rules-of-your-own)) is deliberately
per-machine and gitignored — but a team often wants the *same* set of project rules everywhere,
without pasting a file around by hand. `lane rules pull` fetches one from a git repo you point it
at, and keeps it in a second, separate file so it is never mixed with — and never overwrites —
whatever you have typed into `registry/rules.yaml` yourself.

```sh
lane rules pull git@github.com:your-org/repolane-rules.git   # first pull
lane rules pull                                                # re-pull the same URL, pinned SHA-checked
lane rules pull --latest                                       # intentionally move the pin forward
lane rules status                                               # what is pinned, what is loaded
```

### What the shared repo looks like

At its root:

- `rules.yaml` — **required.** The same schema as `registry/rules.yaml`
  ([field table](rules.md#rules-of-your-own)): `rules:`, a list of maps, `when`/`deny`/`ref`, and
  an `example:` for every rule so `lane doctor` can verify it is actually refused.
- `scripts.d/` — **optional.** Files here are copied (never symlinked) into your local
  `scripts/local/` — see above.
- `knowledge.d/` — **optional.** Plain markdown, copied (never symlinked) into
  `knowledge/shared/` — never directly into `knowledge/`, so a shared file can never silently
  overwrite or shadow one you typed by hand. Unlike `rules.yaml` and `scripts.d/`, these files
  aren't enforced by anything — they're read by a session like the rest of `knowledge/`, not
  validated or executed.

### The security properties, on purpose

- **Pinned, never tracking a branch tip.** The first `lane rules pull <url>` records the exact
  commit SHA it fetched, in `registry/config.yml`. Every later `lane rules pull` with no
  arguments re-fetches, diffs the new commit against the pinned one, and refuses to advance past
  it without confirmation. Only `lane rules pull --latest` intentionally moves the pin. A team's
  guard rules drifting silently, because someone's machine quietly tracked `main`, is exactly the
  failure this is built to prevent.
- **Copied, never symlinked or live-mounted.** The pulled repo lives in a gitignored cache
  (`registry/.shared-cache/`); nothing under `registry/` or `scripts/local/` ever points into it.
  A cache directory that goes away, or gets tampered with between pulls, cannot silently change
  what is enforced — only an explicit `lane rules pull` does that, and it re-verifies the pin
  each time.
- **A separate file, never merged into your own.** Shared rules land in
  `registry/rules.shared.yaml`, not `registry/rules.yaml`. `scripts/hooks/guard.py`'s
  `load_rules()` reads every `registry/rules.*.yaml` file and unions them — through the *exact*
  same parsing, validation and `deny`-only enforcement path, no special case for a shared-sourced
  rule. A malformed or broken shared rule is caught by `lane doctor` exactly the way a broken
  local one already is.
- **Namespaced ids.** A rule pulled from a shared source has its `id` prefixed (`shared-<id>`,
  or `<repo-name>-<id>` when the shared repo names itself), so it cannot silently collide with —
  or shadow — a rule you wrote by hand.
- **Duplicate ids are rejected, not merged.** If a namespace prefix isn't enough — two rules
  genuinely end up with the identical id, in one file or across `registry/rules.yaml` and
  `registry/rules.shared.yaml` — the loader keeps the first one enforced and refuses the rest,
  reported by `lane doctor` exactly like any other broken rule. Two rules sharing an id would
  otherwise make `lane doctor`'s own per-rule verification meaningless (it couldn't tell which
  one actually fired), so this is checked structurally, not left to convention.
- **`knowledge.d/` never overwrites your own knowledge.** A shared `knowledge.d/preferences.md`
  cannot collide with a local `knowledge/preferences.md` — it lands in the separate
  `knowledge/shared/` namespace instead, the same "copied into a clearly-separate location, never
  merged into what you already have" principle as `registry/rules.shared.yaml`.
- **No remote code.** This deliberately supports only a declarative `rules.yaml` (structurally
  validated, and the loader can only ever add a `deny` — see
  [`docs/rules.md`](rules.md#rules-of-your-own)) and a directory of plain scripts you can read
  before they land in `scripts/local/`. It does **not** support pulling custom Python guard logic
  (an eventual `registry/rules.d/*.py`, if this codebase ever grows one) from a remote source —
  running someone else's code inside your own `PreToolUse` hook is a different risk category
  than a rule file that can only refuse things, and this feature does not go there.

### `lane doctor`

Two advisories, both non-blocking:

- `scripts/local/<name>` shadowed by a built-in — see above.
- The pinned shared-rules SHA is behind the shared repo's real `HEAD` (a cheap
  `git ls-remote`). This one line is printed more prominently than the other advisories — team
  guard-rule drift is a different severity of problem than one person's stale local cache — but
  it still never blocks, and never pulls anything itself.

## Tracking your control plane's own files in a private fork

The defaults in `.gitignore` — `registry/*.yaml` (repo list, rules), `scripts/local/` — exist
because this repo is public: a fork inherits whatever is committed here, and nobody wants their
repo names or internal rules shipped in a public template. If your control plane itself lives in a
private fork, that constraint doesn't apply to you, and a team might reasonably want
`registry/repos.yaml` or `registry/rules.yaml` tracked so everyone's checkout starts from the same
state instead of each person hand-building their own.

### `private: true` — the supported mechanism

Set `private: true` in `registry/config.yml` and re-run `lane init` (it asks about this
interactively too, the same way it asks about the tracker — or pass `--private`/`--public`
non-interactively). It rewrites `.gitignore` so `registry/repos.yaml`, `registry/rules.yaml` and
`scripts/local/` are genuinely tracked instead of ignored, and leaves every other ignore rule —
`repos/`, `lanes/`, `memory/`, `knowledge/`, `.cache/`, `registry/rules.shared.yaml`,
`registry/.shared-cache/`, `registry/secrets-ignored.yaml` — exactly as it was: those stay
ignored regardless of `private:`, since they're either machine-rebuildable state or already have
their own separate sharing mechanism (`lane rules pull`, above). Safe to re-run, and safe to flip
back to `private: false` later — `lane init` applies whichever state `config.yml` currently says,
every time.

### The manual override, for just one file

If you want to track only *one* of the three files rather than all of them, `private: true` is
too broad — use the manual recipe instead:

```
git add -f registry/repos.yaml        # force-add despite .gitignore
```

or remove that one specific line from `.gitignore` by hand so it stops being ignored at all. This
is the fallback for a partial case; `private: true` is the supported mechanism for the common one
(a whole team tracking all three together).

**The real tradeoff**: once a file is tracked, it participates in `lane upgrade`'s fast-forward
check exactly like any other tracked file (`guard.py`, `.claude/settings.json`, …). A local edit to
it will block the automated upgrade the same way editing `guard.py` directly does, and you'll be
following the manual recipe in
[Troubleshooting → "Upgrade friction"](troubleshooting.md#upgrade-friction-the-clone-is-the-control-plane)
for it going forward. That's usually the right tradeoff for a file a whole team edits together, but
it's a real cost, not a free upgrade to "shared state" — weigh it per file, not all at once.
