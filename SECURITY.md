# Security

Repolane is a local tool: no server, no account, and no shared infrastructure between
installs. A vulnerability here almost always means one thing — a way to get the guard
(`scripts/hooks/guard.py`) to allow something it should refuse: a path that escapes the
lane, a chained command that slips past a rule, a way to read a secret file.

## Reporting one

Open an [issue](https://github.com/aj-oss-tools/repolane/issues). There is nothing to
disclose privately to — no server, no account, no other tenant whose exposure depends on
quiet, fast patching — so a public issue is the right place and gets it fixed faster than
any private channel would.

Describe the *class* of the problem rather than posting a full working exploit in the same
breath: what kind of command or path shape gets through, not a ready-to-run repro. Every
existing install stays exposed to a bypass for as long as it is both public and unpatched,
so naming the class is enough for it to get found and fixed without also handing out a
working bypass to everyone else running it in the meantime.

## What's in scope

The guard's actual behaviour — anything `docs/rules.md` says should be refused, and isn't,
or is refused for the wrong reason. Also in scope: the board (`lane board`) reaching beyond
`127.0.0.1`, making an outbound call, or leaking a secret's contents rather than its key
name — see [the security model page](https://repolane.dev/docs/security/) for what it's
meant to guarantee and what it's a guardrail against rather than a hardened boundary for.

Not in scope: anything that requires an attacker who already has write access to your own
repos or your own machine — that party already has more access than the guard is trying to
withhold from an agent session.
