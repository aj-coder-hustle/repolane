# Lane

**One piece of work at a time, across all your repos.**

Working on several repos at once, with several things in flight, turns into a mess: which branch
was that on, which checkout is current, what was I doing last Tuesday. Lane is a control plane for
that. One folder holds every repo you work on, every piece of work in progress, and everything
Claude has learned about how you work.

```sh
lane start ABC-123 web api      # a branch and a worktree in each repo, from the default branch
cd lanes/ABC-123 && claude      # Claude opens knowing what this work is
lane park ABC-123 "waiting on review"
lane done ABC-123               # removes the folders once everything is pushed
```

## Install

```sh
git clone https://github.com/aj-coder-hustle/lane.git && cd lane
./lane install        # puts `lane` and the long-form commands on your PATH
lane init             # asks two questions, sets the machine up
lane add <git-url>    # or: lane add ~/path/to/a/checkout/you/already/have
```

Requires **git**, **python3** and **bash**. The GitHub CLI (`gh`) is optional — without it you lose
pull request status and `lane gh`. Claude Code is optional too: the commands all work on their own,
and the hooks only matter when Claude is driving.

Tested on macOS and Linux. Windows works under WSL.

## The idea

A **lane** is one piece of work, which may span several repos. Starting one gives you a folder with
a worktree of each repo it touches, all on the same branch.

```
lanes/ABC-123/
  web/     a worktree of repos/web on branch ABC-123
  api/     a worktree of repos/api on branch ABC-123
  refs/    anything you attached for reference
```

Repos live once, in `repos/`, as mirrors that stay clean and stay on their default branch. Every
lane's worktrees share that object store, so a second piece of work costs a checkout of files
rather than a full clone — and switching between them is instant.

You run Claude from `lanes/<id>/`, never from inside one of the repos. No repo is the main one.

## Everything else

```
lane status     where everything stands        lane board    the same thing in a browser
lane import     past Claude conversations      lane note     write something worth remembering
lane run/gh     run a command in one repo without leaving the lane
lane merge      two pieces of work turned out to be one
lane help       the full list
```

`lane board` opens a local web page — a git client scoped to your work, with diffs, a commit box,
history, notes and memory. It binds to `127.0.0.1` only and sends nothing anywhere.

## Why it refuses things

Lane is opinionated about what a Claude session may touch, and every refusal exists because the
alternative went wrong at least once.

- A session is fenced into the lane it belongs to: no reading other lanes, no reading the mirrors,
  nothing outside the folder.
- `.env` and credential files are never readable — not even with permission, because the values
  would end up in a transcript. `lane keys <path>` gives you the key names instead.
- Pushing to `main`, `master` or `develop` needs an explicit marker you can see. Remotes may never
  be added, changed or removed.
- Memory is never written silently: Claude drafts, then asks which of the four scopes it belongs
  in, so everything does not quietly become a permanent global preference.
- New branches start from the default branch. Commits are proposed, not made behind your back.

`docs/rules.md` explains each one and why. `lane doctor` checks the rules are actually in force,
and fails loudly if the guard has stopped refusing.

## Documentation

- [`docs/concepts.md`](docs/concepts.md) — the five words the whole system is built from. Start here.
- [`docs/rules.md`](docs/rules.md) — every refusal, and the failure behind it.
- [`docs/board.md`](docs/board.md) — the web board.

## License

MIT — see [LICENSE](LICENSE).
