# `knowledge/` — preferences, conventions, domain notes

Where [`../memory/`](../memory/README.md) holds facts a session *discovered*, this folder holds
things you decided. Nothing in here is auto-loaded into every session: it is read deliberately, by
whatever needs it.

```
knowledge/
  preferences.md          how you want to be worked with — read before any session writes code
  preferences.md.example  a starting point, copied by `lane init`
  conventions/            house style: naming, testing, review, commit shape
  domains/<name>.md       what a part of the product actually means
```

## `preferences.md`

The `pref` memory scope: true in all work, forever. `lane init` copies the example if you have no
file yet, and `lane-memory file <slug> pref` appends to it.

It is prose, not configuration — nothing parses it. Keep it short enough that reading it is never a
decision. The example covers communication, what to discuss before acting, commits and branches,
and code style; delete what does not apply to you and add what does.

## `conventions/`

House rules that outlive any one repo — how branches are named, what a commit should contain, what
you expect in a review, when a test is required. Split them however you like; nothing here is
loaded automatically, so a session reads a file when the work calls for it.

If a convention is genuinely specific to one repo, it belongs in that repo's own `CLAUDE.md`
instead, where the guard injects it the first time a session touches that repo.

## `domains/<name>.md`

Things that are true about your product rather than your code: what "settlement" means, which of the
four things called `account` is the one people mean, the states an order can be in and who may move
it between them.

A lane picks one up by naming it — mention the domain in the lane's `## Goal` and a session reading
the spec knows to open `knowledge/domains/<name>.md`. The `context-loader` agent does this
explicitly as step four of its brief.

Domain notes are usually the highest-value thing in this folder and the least often written. They
are what stops a session from confidently implementing the wrong meaning of a word.

## Writing to it

Like `memory/`, this folder is gated: the guard refuses direct writes from a lane session, and
preferences are appended through `lane-memory file <slug> pref` so the scope is a choice someone
made rather than a default. Editing an existing file is allowed from a dispatcher session at the
control plane root.
