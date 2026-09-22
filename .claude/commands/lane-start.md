---
description: Start new work — Claude picks the id, runs lane-start, enters the worktree, writes the Goal
argument-hint: <what you want to build> [on <repo>]
---
Request: $ARGUMENTS
1. Propose in ONE line: id (ticket key if present, else a kebab slug), repo(s), base branch. Ask "go?" and stop.
2. On yes: run `"$CLAUDE_PROJECT_DIR"/bin/lane-start <id> <repo> ...` and show its output.
3. EnterWorktree with name="<id>" — the lane id, never a path and never a repo. It lands you at the lane root with every repo reachable. Say so.
4. Draft the Goal section of registry/lanes/<id>.md from the request, show it, write it once they say ok. Then wait.
