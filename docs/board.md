# The board

`lane board` opens a local web page. It is a git client scoped to your work, and it replaces
reaching for a desktop git app.

It serves only to your own machine and reads the same files the commands do. Nothing is sent
anywhere.

## Three places

**Home** is what opens: the work you have in progress, what each piece touches, and what needs
attention.

**Work** is one piece of work. The repos it spans, the files you have changed, the diff of the one
you picked, and a commit box. Side panels cover History, Notes, Refs, Spec and past Sessions.

**Memory** browses the four scopes and what is in each.

Press the jump control in the top bar, or Command-K, to move between pieces of work without going
back Home.

## Multiple registered planes

If your machine has more than one registered control plane (`~/.local/share/lane/planes.json` —
see ["The clone is the control plane"](concepts.md#the-clone-is-the-control-plane) and `lane use`
in [`docs/commands.md`](commands.md)), a plane switcher appears next to the `lane-board` brand in
the top bar. The board opens showing whichever plane the server was actually started from/inside
— the least surprising default, matching "I opened the board from this project" — and picking a
different registered plane from the dropdown reloads the board's data scoped to that plane,
in place, without starting a second server process or needing a second browser tab. The page
title always names the plane currently shown.

Switching which plane's data is being *read* needs nothing extra — it is read-only. Any
state-changing action the board already supports (stage, commit, push, pull, discard, amend,
start/resume/park/done) is still validated server-side against the registry on every request and
only ever applies to the plane it is scoped to; the server never trusts a plane name from the
client beyond "is this actually a name in `planes.json`". The board still binds `127.0.0.1` only
and still requires the per-run `X-Token` header for every state-changing route — switching planes
does not loosen either.

## Notes

Ticket keys link wherever `tracker.url` in `registry/config.yml` points. Blank means keys show as
plain text.

Secret files are never shown: the server drops them by path before git is asked for any content.

The page is plain HTML, CSS and JavaScript with no build step. It makes one outbound request —
its typefaces come from Google Fonts. Delete the two `<link>` tags at the top of
`scripts/board/index.html` if you would rather it made none; the board falls back to your system
font and nothing else changes.
