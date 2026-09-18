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

## Notes

Ticket keys link wherever `tracker.url` in `registry/config.yml` points. Blank means keys show as
plain text.

Secret files are never shown: the server drops them by path before git is asked for any content.

The page is plain HTML, CSS and JavaScript with no build step, and makes no network calls beyond
its own server.
