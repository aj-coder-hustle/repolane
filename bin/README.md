# `bin/` — the long-form commands

One symlink per command, pointing at the real script in `../scripts/`. `lane install` links
everything in this folder onto your `PATH`.

Two names exist for the same thing on purpose:

- **`lane <command>`** is what a person types. `../lane` is a dispatcher that maps one word to one
  script.
- **`lane-<command>`** is what the guard messages, the agent prompts, the slash commands and the
  docs tell a session to type — because it runs from any directory with no `cd`, which is exactly
  the constraint a session is under.

They are the same code either way. Adding a command means adding a symlink here as well as a line
in `../lane`; `../scripts/README.md` has the checklist.

The names do not always match the script: `lane-status` points at `status-all`, `lane-audit` at
`branch-audit`, `lane-help` and `lane-menu` both at `menu`, `lane-init` at `init`, and
`lane-repo-add` at `repo-add`.

<!-- audit: verifying the required test check gates merges. This line is removed with the branch. -->
