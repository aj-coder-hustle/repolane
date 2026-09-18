# Why it refuses things

Every refusal here exists because the alternative went wrong. If you hit one, this page says why.

## Stay in the lane you are in

A session belongs to one piece of work. It cannot read other lanes, the mirrors, or anything
outside this folder. Without this, a session asked to fix one bug quietly reads four repos, fills
its context with unrelated code, and starts making changes nobody asked for.

Need something outside? Attach it once with `lane ref` and read it at `lanes/<id>/refs/<name>`.
The hook refuses writes through a reference unless it was attached with `--rw`. It is a symlink
underneath, so this constrains the session, not you.

## Do not enter a repo

The session sits at `lanes/<id>/`, never inside `lanes/<id>/<repo>/`. Entering one makes that repo look
like the main one, and multi-repo work degrades into single-repo work. Nothing needs it:
`lane run <repo> <cmd>`, `lane gh <repo> <args>`, `git -C <repo>`, and editing `<repo>/file` all work
from where you are.

## The mirrors are read-only

`repos/<name>` stays on its default branch and clean, because every worktree shares its object
store. Work in a worktree.

## The control plane is edited from the root

Scripts, rules, the registry and memory are changed from a session started at the top, not from
inside a lane. A lane editing the rules that constrain it is how you lose the rules.

## Never read `.env` or credential files

Not even when you grant permission: the read itself is the problem, because the values end up in a
transcript. Structure is available instead, via `.env.example` or `lane keys <path>`, which lists key
names and never values.

## Pushing to a default branch needs your word

`main`, `master` and `develop` are refused. When you do mean it, the command carries a marker you
can see: `ALLOW_DEFAULT_BRANCH_PUSH=1 git push …`. Remotes may never be added, changed or removed.

## Memory is never written directly

Claude drafts, then asks which of the four scopes it belongs in. Left alone, everything becomes a
permanent global preference, and within a month the system is full of things that were true once.

## New branches start from the default branch

Not from whatever happens to be checked out.

## Ask before committing

Commits are proposed, and shaped as coherent units: neither one commit per edit nor one enormous
commit at the end.

`lane doctor` checks two things: that the guard compiles and still refuses a known-denied probe,
and that every lane and worktree is still wired to it. A session whose `settings.local.json` lost
its hooks is unguarded even when the guard itself is perfectly healthy, so both are checked.
