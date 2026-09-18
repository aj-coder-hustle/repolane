#!/usr/bin/env python3
"""lane-board: local web UI for lanes. Binds 127.0.0.1 only. Plain stdlib.

GET  /                      page (token injected)
GET  /api/board             lanes + per-repo state
GET  /api/repo              ?lane=&repo=   files, log, branch, pr, sessions
GET  /api/diff              ?lane=&repo=&file=&staged=0|1
GET  /api/show              ?lane=&repo=&sha=   one commit
GET  /api/spec              ?lane=         lane markdown
GET  /api/brief             ?lane=         lane-brief output
POST /api/stage             {lane,repo,files:[..],stage:bool}
POST /api/discard           {lane,repo,files:[..]}   throws away uncommitted changes
POST /api/amend             {lane,repo,message}      rewrites the last commit, refused once pushed
POST /api/commit            {lane,repo,message}
POST /api/push | /api/pull  {lane,repo}
POST /api/lane                {action:start|resume|park|done, id, repos?, note?}
Every /api call needs header X-Token (printed at start, embedded in the page).
Never operates on repos/ (mirrors). Never returns, stages or commits secret files.
"""
import glob, json, os, re, secrets, subprocess, sys, threading, time, urllib.parse, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.realpath(__file__))
AD = os.path.dirname(os.path.dirname(HERE))
LANES, REPOS, LANES_DIR, BIN = f"{AD}/lanes", f"{AD}/repos", f"{AD}/registry/lanes", f"{AD}/bin"
TOKEN = secrets.token_urlsafe(24)
PORT = int(os.environ.get("WS_BOARD_PORT", "7777"))
SECRET = re.compile(r"(^|/)(\.env(\.[\w.-]+)?|[^/]*\.(pem|key|p12|pfx)|[^/]*credentials[^/]*\.json|secrets?\.(json|ya?ml|toml))$")
SAFE_SUFFIX = re.compile(r"\.(example|sample|template|dist)$")
PR_CACHE = {}
DEFAULTS = {}
STARTED = time.strftime("%Y-%m-%dT%H:%M:%S")
DIFF_LIMIT = 2000
STATIC = {"/board.css": "text/css", "/board.js": "text/javascript"}

def sh(args, cwd=None, timeout=60, inp=None):
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=timeout, input=inp)
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return 124, "", "timed out"

def git(cwd, *a): return sh(["git", "-C", cwd, *a])[1].rstrip("\n")

def defaults():
    """Each repo's integration branch as the registry declares it. The remote's own HEAD can be
    stale - api still advertises master while the team moved to develop - so the
    registry wins over git here."""
    t = open(f"{AD}/registry/repos.yaml").read()
    out = {m.group(1): m.group(2) for m in
           re.finditer(r"^  ([\w.-]+):\n(?:    .*\n)*?    default_branch: (\S+)", t, re.M)}
    # compare_branch overrides default_branch where a repo integrates somewhere else
    out.update({m.group(1): m.group(2) for m in
                re.finditer(r"^  ([\w.-]+):\n(?:    .*\n)*?    compare_branch: (\S+)", t, re.M)})
    return out

def shorts():
    t = open(f"{AD}/registry/repos.yaml").read()
    return {m.group(1): m.group(2) for m in re.finditer(r"^  ([\w.-]+):\n(?:    .*\n)*?    short: (\S+)", t, re.M)}

def lane_files(): return sorted(f for f in os.listdir(LANES_DIR) if f.endswith(".md"))

def parse_ws(path):
    t = open(path).read()
    head = t.split("---")[1] if t.startswith("---") else ""
    g = lambda k: (re.search(rf"^{k}: *(.*)$", head, re.M) or [None, ""])[1].strip()
    repos = [{"repo": m.group(1), "branch": m.group(2), "base": m.group(3)}
             for m in re.finditer(r"^  - repo: (\S+)\n    branch: (\S+)\n(?:    base: (\S+))?", head, re.M)]
    refs = [dict(path=m.group(1), **dict(re.findall(r"    (\w+): (.*)", m.group(2)))) for m in re.finditer(r"^  - path: (.+)\n((?:    .*\n?)*)", head, re.M)]
    # Stop at the NEXT heading of any kind, not at one named heading: the resume note is
    # followed by ## Findings, and reading through to ## Log swallowed it.
    sect = lambda name, nxt=None: (re.search(rf"## {name}\n(.*?)(?=\n## |\Z)", t, re.S) or [None, ""])[1].strip()
    findings = (re.search(r"## Findings\n(.*?)(?=\n## |\Z)", t, re.S) or [None, ""])[1].strip()
    return {"id": os.path.basename(path)[:-3], "status": g("status"), "ticket": g("ticket"), "updated": g("updated"),
            "repos": repos, "refs": refs, "findings": findings, "goal": sect("Goal"),
            "note": re.sub(r"^_(\d{4}-\d{2}-\d{2})_:\s*", r"\1 — ", sect("Resume note"), flags=re.M)}

def repo_state(path):
    if not os.path.exists(f"{path}/.git"): return {"exists": False}
    st = git(path, "status", "--porcelain")
    dirty = len([l for l in st.splitlines() if l])
    up = git(path, "rev-parse", "--abbrev-ref", "@{u}")
    ahead = git(path, "rev-list", "--count", "@{u}..HEAD") if up else None
    behind = git(path, "rev-list", "--count", "HEAD..@{u}") if up else None
    # when HEAD last moved: Home says "touched today" rather than making you read a date
    last = git(path, "log", "-1", "--format=%ct")
    # how far this branch has drifted from the default branch it came from, which is the
    # thing that makes a 12-file change painful to land and is invisible in ahead/behind
    base = git(path, "rev-parse", "--abbrev-ref", "origin/HEAD").split("/")[-1] or "master"
    off = git(path, "rev-list", "--count", f"HEAD..origin/{base}")
    return {"exists": True, "branch": git(path, "branch", "--show-current"), "upstream": up or None,
            "dirty": dirty, "ahead": int(ahead) if ahead and ahead.isdigit() else None,
            "behind": int(behind) if behind and behind.isdigit() else None,
            "last": int(last) if last.isdigit() else None,
            "base_branch": base, "base_behind": int(off) if off.isdigit() else None}

def pr_live_failing(pr_):
    """Failing means "something to act on now". A merged or closed PR is history - one of its
    checks may have gone red weeks ago, and reporting that forever makes a finished repo look
    broken. Only an open PR can be failing."""
    if not isinstance(pr_, dict) or pr_.get("state") != "OPEN": return False
    return bool((pr_.get("checks") or {}).get("failing"))

def rebase_target(path, r, pr_, spec_base=None):
    """How far behind the branch this work will actually merge into.

    The compare branch is a property of the repo, declared in registry/repos.yaml
    (compare_branch, else default_branch). Not the remote's HEAD, which goes stale -
    api still advertises master while the team integrates on develop - and not a
    PR's base, which can point at a one-off branch and, once merged, is history.
    A lane's recorded base is used only for a repo the registry does not define.
    Getting this wrong understates drift: measured against master a branch read as 10 behind
    when against develop it was 40."""
    reg = DEFAULTS.get(r.get("repo") or "")
    base = reg or spec_base
    src = "registry" if reg else ("lane" if spec_base else None)
    if not base or base == r.get("base_branch"):
        if base and base == r.get("base_branch"): r["base_source"] = src or "default"
        return
    off = git(path, "rev-list", "--count", f"HEAD..origin/{base}")
    if not off.isdigit(): return          # no such remote branch: keep what we had
    r["base_branch"] = base
    r["base_behind"] = int(off)
    r["base_source"] = src
    r["base_from_pr"] = src == "pr"

def board_uncached():
    sh_ = shorts(); out = []
    for f in lane_files():
        w = parse_ws(f"{LANES_DIR}/{f}")
        for r in w["repos"]:
            p = f"{LANES}/{w['id']}/{r['repo']}"; r.update(repo_state(p)); r["short"] = sh_.get(r["repo"], r["repo"]); r["path"] = p
            if r.get("exists"):
                fl = files(p); r["staged"] = sum(1 for f in fl if f["staged"]); r["unstaged"] = sum(1 for f in fl if f["unstaged"])
                cached = PR_CACHE.get((p, r.get("branch")))
                pr_ = cached[1] if cached else None
                r["pr_failing"] = pr_live_failing(pr_)
                r["pr_state"] = pr_.get("state") if isinstance(pr_, dict) else None
                rebase_target(p, r, pr_, r.get("base"))
        out.append(w)
    order = {"active": 0, "parked": 1}
    out.sort(key=lambda w: (order.get(w["status"], 2), w["id"].lower()))
    return {"lanes": out, "repos": sorted(os.listdir(REPOS)), "generated": time.strftime("%H:%M:%S"), "serverStartedAt": STARTED,
            "tracker": tracker_url()}

def lane_path(lane, repo):
    p = os.path.realpath(f"{LANES}/{lane}/{repo}")
    if not p.startswith(os.path.realpath(LANES) + "/") or not os.path.exists(f"{p}/.git"):
        raise ValueError("not a lane worktree")
    return p

def numstat(path, cached):
    out = sh(["git", "-C", path, "diff", "--numstat", *(["--cached"] if cached else [])])[1]
    res = {}
    for l in out.splitlines():
        parts = l.split("\t")
        if len(parts) >= 3:
            a, d, name = parts[0], parts[1], parts[-1]
            if " => " in name: name = name.split(" => ")[-1].rstrip("}")
            res[name] = (int(a) if a.isdigit() else None, int(d) if d.isdigit() else None)
    return res

def files(path):
    _, out, _ = sh(["git", "-C", path, "status", "--porcelain=v1", "-z", "--untracked-files=all"])
    ns_w, ns_c = numstat(path, False), numstat(path, True)
    items = out.split("\0"); res = []; i = 0
    while i < len(items):
        e = items[i]; i += 1
        if not e: continue
        x, y, name = e[0], e[1], e[3:]
        old = None
        if x in "RC" and i < len(items): old = items[i]; i += 1
        staged = x not in " ?"; unstaged = y not in " " or x == "?"
        cnt = ns_c.get(name) if staged and not unstaged else ns_w.get(name) if unstaged and not staged else None
        res.append({"file": name, "old": old, "index": x.strip(), "work": y.strip(), "untracked": x == "?",
                    "staged": staged, "unstaged": unstaged, "partial": staged and unstaged and x != "?",
                    "secret": is_secret(name), "add": cnt[0] if cnt else None, "del": cnt[1] if cnt else None,
                    "add_staged": (ns_c.get(name) or (None, None))[0], "del_staged": (ns_c.get(name) or (None, None))[1]})
    return sorted(res, key=lambda r: r["file"])

def is_secret(name):
    return bool(SECRET.search(name)) and not SAFE_SUFFIX.search(name)

def compare_branch(repo, spec_base=None):
    """The branch this repo integrates into - registry first, the lane's record second."""
    return DEFAULTS.get(repo) or spec_base

def work_range(path, repo, spec_base=None):
    """`origin/<base>..HEAD`: the commits this branch added since it left its base.

    Without this the history panel lists whatever is reachable from HEAD, which on a branch
    40 behind develop is mostly other people's commits that arrived with the base."""
    base = compare_branch(repo, spec_base)
    if not base: return None
    if not git(path, "rev-parse", "--verify", "--quiet", f"origin/{base}"): return None
    return f"origin/{base}..HEAD"

def log(path, n=15, rng=None):
    args = ["log", f"-{n}", "--format=%h%x1f%s%x1f%an%x1f%ar%x1f%cI%x1f%D"]
    if rng: args.append(rng)
    out = git(path, *args)
    return [dict(zip(["sha", "subject", "author", "when", "date", "refs"], l.split("\x1f"))) for l in out.splitlines() if l]

def lane_log(lane, n=60, whole=False):
    """Every repo of a lane, interleaved newest first. Each row says which repo it came from,
    because across four repos a subject line alone does not tell you where you are."""
    f = f"{LANES_DIR}/{lane}.md"
    if not re.fullmatch(r"[\w.-]+", lane) or not os.path.exists(f): raise ValueError("unknown lane")
    spec = parse_ws(f); sh_ = shorts(); rows = []
    for r in spec["repos"]:
        p = f"{LANES}/{lane}/{r['repo']}"
        if not os.path.exists(f"{p}/.git"): continue
        rng = None if whole else work_range(p, r["repo"], r.get("base"))
        for c in log(p, n, rng):
            c["repo"] = r["repo"]; c["short"] = sh_.get(r["repo"], r["repo"]); rows.append(c)
    rows.sort(key=lambda c: c.get("date") or "", reverse=True)
    return rows[:n]

def pr(path, branch):
    key = (path, branch); now = time.time()
    if key in PR_CACHE and now - PR_CACHE[key][0] < 90: return PR_CACHE[key][1]
    code, out, err = sh(["gh", "pr", "view", branch, "--json",
                         "number,title,state,url,isDraft,reviewDecision,statusCheckRollup,mergeable,baseRefName"], cwd=path, timeout=25)
    res = None
    if code == 0:
        try:
            d = json.loads(out); checks = d.get("statusCheckRollup") or []
            bad = [c for c in checks if (c.get("conclusion") or c.get("state") or "").upper() not in ("SUCCESS", "NEUTRAL", "SKIPPED", "")]
            pend = [c for c in checks if (c.get("status") or "").upper() in ("IN_PROGRESS", "QUEUED", "PENDING")]
            d["checks"] = {"total": len(checks), "failing": len(bad), "pending": len(pend)}; d.pop("statusCheckRollup", None); res = d
        except Exception: res = None
    elif "no pull requests found" not in (err or "").lower() and "not found" not in (err or "").lower():
        res = {"error": (err or "gh failed").strip()[:200]}
    PR_CACHE[key] = (now, res); return res

def next_action(st, fl, pr_):
    """One primary action per repo, first matching rule (docs/board-design.md §1)."""
    if not st.get("exists"): return {"id": "resume", "label": "Resume lane"}
    staged = sum(1 for f in fl if f["staged"]); unst = sum(1 for f in fl if f["unstaged"])
    ahead, behind, up = st.get("ahead") or 0, st.get("behind") or 0, st.get("upstream")
    if up and behind > 0 and unst == 0 and staged == 0: return {"id": "pull", "label": f"Pull {behind}"}
    if staged: return {"id": "commit", "label": f"Commit {staged} file{'s' if staged != 1 else ''}"}
    if unst: return {"id": "stage_all", "label": f"Stage all {unst}"}
    if not up: return {"id": "publish", "label": "Publish branch"}
    if ahead: return {"id": "push", "label": f"Push {ahead}"}
    if pr_ is None: return {"id": "create_pr", "label": "Create PR"}
    if isinstance(pr_, dict) and pr_.get("error"): return {"id": "none", "label": "Nothing to do"}
    state = (pr_.get("state") or "").upper(); ch = pr_.get("checks") or {}
    if state == "MERGED": return {"id": "finish", "label": "Finish lane"}
    if state == "OPEN":
        if ch.get("failing"): return {"id": "open_pr", "label": f"Open PR — {ch['failing']} failing", "tone": "bad", "url": pr_.get("url")}
        if ch.get("pending"): return {"id": "open_pr", "label": "Open PR — checks running", "url": pr_.get("url")}
        if (pr_.get("reviewDecision") or "") == "CHANGES_REQUESTED": return {"id": "open_pr", "label": "Open PR — changes requested", "tone": "warn", "url": pr_.get("url")}
        return {"id": "open_pr", "label": f"Open PR #{pr_.get('number')}", "tone": "ok", "url": pr_.get("url")}
    return {"id": "none", "label": "Nothing to do"}

def compare_url(path, base):
    origin = git(path, "remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", origin)
    if not m: return None
    br = git(path, "branch", "--show-current"); base = (base or "").replace("origin/", "") or git(path, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD").replace("origin/", "")
    return f"https://github.com/{m.group(1)}/{m.group(2)}/compare/{base}...{br}?expand=1"

def sessions(repo):
    code, out, _ = sh([f"{BIN}/lane-sessions", repo, "8"]); return out if code == 0 else ""

def diff(path, file, staged, show_all=False):
    if is_secret(file):
        repo = os.path.basename(path)
        return {"secret": True, "mirror": f"repos/{repo}/{file}", "diff": "", "total_lines": 0, "truncated": False}
    rel = file
    if staged: out = sh(["git", "-C", path, "diff", "--cached", "--", rel])[1]
    else:
        st = [f for f in files(path) if f["file"] == rel]
        if st and st[0]["untracked"]: out = sh(["git", "-C", path, "diff", "--no-index", "--", "/dev/null", rel])[1]
        else: out = sh(["git", "-C", path, "diff", "--", rel])[1]
    lines = out.split("\n"); total = len(lines)
    binary = any(l.startswith("Binary files") for l in lines[:12])
    if binary or total > 50000:
        try: size = os.path.getsize(f"{path}/{rel}")
        except OSError: size = 0
        return {"binary": True, "size": size, "diff": "", "total_lines": total, "truncated": False}
    if not show_all and total > DIFF_LIMIT:
        return {"diff": "\n".join(lines[:DIFF_LIMIT]), "total_lines": total, "truncated": True}
    return {"diff": out, "total_lines": total, "truncated": False}

def show(path, sha, show_all=False):
    """The diff of one commit. Secret files are dropped from the path list before git shows anything,
    so their contents can never reach the page — the same rule the file diff follows."""
    if not re.fullmatch(r"[0-9a-fA-F]{4,40}", sha or ""):
        return {"error": "bad commit id"}
    rc, meta, err = sh(["git", "-C", path, "show", "-s",
                        "--format=%H%n%h%n%an%n%ad%n%s%n%b", "--date=format:%d %b %Y %H:%M", sha])
    if rc != 0:
        return {"error": (err or "no such commit").strip()}
    m = meta.split("\n")
    info = {"sha": m[0], "short": m[1], "author": m[2], "date": m[3], "subject": m[4],
            "body": "\n".join(m[5:]).strip()}
    touched = [f for f in sh(["git", "-C", path, "show", "--name-only", "--format=", sha])[1].split("\n") if f.strip()]
    safe = [f for f in touched if not is_secret(f)]
    info["files"] = len(touched)
    info["hidden"] = len(touched) - len(safe)
    if not safe:
        return {**info, "diff": "", "total_lines": 0, "truncated": False}
    out = sh(["git", "-C", path, "show", "--format=", sha, "--"] + safe)[1]
    lines = out.split("\n"); total = len(lines)
    if any(l.startswith("Binary files") for l in lines[:12]) and total < 20:
        return {**info, "diff": out, "total_lines": total, "truncated": False}
    if not show_all and total > DIFF_LIMIT:
        return {**info, "diff": "\n".join(lines[:DIFF_LIMIT]), "total_lines": total, "truncated": True}
    return {**info, "diff": out, "total_lines": total, "truncated": False}

def discard(path, names):
    """Throw away uncommitted changes to the named files. This destroys work that git cannot get back,
    so it is deliberately narrow: named files only, never a whole-tree reset, and never a secret file."""
    if not names:
        return {"error": "no files given"}
    known = {f["file"]: f for f in files(path)}
    tracked, untracked, refused = [], [], []
    for f in names:
        st = known.get(f)
        if st is None:
            refused.append(f"{f}: has no uncommitted change")
        elif is_secret(f):
            refused.append(f"{f}: secret file, discard it yourself if you mean to")
        elif st.get("untracked"):
            untracked.append(f)
        else:
            tracked.append(f)
    if refused:
        return {"error": "\n".join(refused)}
    out = []
    if tracked:
        rc, o, e = sh(["git", "-C", path, "checkout", "--"] + tracked)
        if rc != 0:
            return {"error": (e or o).strip()}
        out.append(f"reverted {len(tracked)} file(s)")
    for f in untracked:
        try:
            os.remove(os.path.join(path, f))
        except OSError as ex:
            return {"error": f"{f}: {ex}"}
    if untracked:
        out.append(f"deleted {len(untracked)} new file(s)")
    return {"output": ", ".join(out)}

def amend(path, message):
    """Rewrite the last commit. Refused once that commit is on the remote — rewriting shared history
    is how people lose each other's work."""
    branch = git(path, "branch", "--show-current")
    upstream = git(path, "rev-parse", "--abbrev-ref", f"{branch}@{{u}}")
    if upstream and not upstream.startswith("fatal"):
        ahead = git(path, "rev-list", "--count", f"{upstream}..HEAD")
        if ahead.strip() in ("", "0"):
            return {"error": f"The last commit is already on {upstream}. Amending it would rewrite shared history — "
                             f"make a new commit instead."}
    args = ["git", "-C", path, "commit", "--amend"]
    args += ["-m", message] if (message or "").strip() else ["--no-edit"]
    rc, o, e = sh(args)
    if rc != 0:
        return {"error": (e or o).strip()}
    return {"output": o.strip() or "amended"}

def tracker_url():
    """Where ticket keys link to, from registry/config.yml. Empty means no tracker configured,
    and the page shows keys as plain text rather than guessing a host."""
    try:
        with open(f"{AD}/registry/config.yml") as fh:
            m = re.search(r"^tracker:\s*$.*?^\s+url:\s*(\S+)\s*$", fh.read(), re.M | re.S)
            return m.group(1).strip().strip("\"'") if m else ""
    except OSError:
        return ""

def run_ws(action, id_, repos=None, note=None):
    if not re.fullmatch(r"[A-Za-z0-9._-]+", id_ or ""): return 1, "", "bad id"
    if action == "start":
        specs = [s for s in (repos or "").split() if re.fullmatch(r"[\w.:@/-]+", s)]
        if not specs: return 1, "", "repos required"
        return sh([f"{BIN}/lane-start", id_, *specs], timeout=300)
    if action == "resume": return sh([f"{BIN}/lane-resume", id_], timeout=300)
    if action == "park":
        if not note: return 1, "", "resume note required"
        return sh([f"{BIN}/lane-park", id_, note], timeout=120)
    if action == "done": return sh([f"{BIN}/lane-done", id_], timeout=120)
    return 1, "", "unknown action"

MEM = f"{AD}/memory"; KNOW = f"{AD}/knowledge"; INBOX = f"{AD}/.cache/memory-inbox"
CROSSISH = re.compile(r"\b(always|never|every repo|all repos|any repo|in every|house style|preference|standing)\b", re.I)

def mem_meta(path):
    try: t = open(path).read()
    except Exception: return None
    g = lambda k: (re.search(rf"^{k}: *(.+)$", t, re.M) or [None, ""])[1].strip().strip('"')
    ty = (re.search(r"type: *(\w+)", t) or [None, ""])[1]
    return {"file": os.path.basename(path), "name": g("name") or os.path.basename(path)[:-3], "description": g("description"),
            "type": ty, "bytes": len(t), "modified": time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(path))),
            "suspect": bool(ty in ("feedback", "user") and CROSSISH.search(t[:800]))}

def memory_tree():
    scopes = []
    cross = [mem_meta(f) for f in sorted(glob.glob(f"{MEM}/*.md")) if os.path.basename(f) not in ("MEMORY.md", "README.md")]
    scopes.append({"id": "cross", "label": "cross-repo", "hint": "true in every repo, forever", "files": [c for c in cross if c]})
    sh_ = shorts()
    for d in sorted(os.listdir(MEM)):
        if not os.path.isdir(f"{MEM}/{d}"): continue
        fl = [mem_meta(f) for f in sorted(glob.glob(f"{MEM}/{d}/*.md")) if os.path.basename(f) not in ("MEMORY.md", "README.md")]
        scopes.append({"id": f"repo:{d}", "label": sh_.get(d, d), "repo": d, "hint": d, "files": [c for c in fl if c]})
    pref = f"{KNOW}/preferences.md"
    scopes.append({"id": "pref", "label": "preferences", "hint": "how Claude works with you",
                   "files": [{"file": "preferences.md", "name": "preferences", "description": "standing working preferences", "type": "user",
                              "bytes": os.path.getsize(pref) if os.path.exists(pref) else 0,
                              "modified": time.strftime("%Y-%m-%d", time.localtime(os.path.getmtime(pref))) if os.path.exists(pref) else "", "suspect": False}]})
    drafts = [mem_meta(f) for f in sorted(glob.glob(f"{INBOX}/*.md"))]
    scopes.append({"id": "drafts", "label": "pending drafts", "hint": "waiting for a scope", "files": [d for d in drafts if d]})
    dups = {}
    for f in glob.glob(f"{MEM}/**/*.md", recursive=True):
        if os.path.basename(f) not in ("MEMORY.md", "README.md"): dups.setdefault(os.path.basename(f), []).append(os.path.relpath(f, AD))
    findings = []
    for f in lane_files():
        w = parse_ws(f"{LANES_DIR}/{f}")
        if w.get("findings") and re.search(r"^- ", w["findings"], re.M):
            findings.append({"id": w["id"], "status": w["status"], "findings": w["findings"]})
    return {"scopes": scopes, "duplicates": {k: v for k, v in dups.items() if len(v) > 1}, "findings": findings,
            "repos": sorted(os.listdir(REPOS))}

def mem_path(scope, file):
    if not re.fullmatch(r"[\w.-]+\.md", file or ""): raise ValueError("bad file")
    if scope == "cross": p = f"{MEM}/{file}"
    elif scope == "pref": p = f"{KNOW}/preferences.md"
    elif scope == "drafts": p = f"{INBOX}/{file}"
    elif scope.startswith("repo:"):
        d = scope[5:]
        if not re.fullmatch(r"[\w.-]+", d): raise ValueError("bad scope")
        p = f"{MEM}/{d}/{file}"
    else: raise ValueError("bad scope")
    rp = os.path.realpath(p)
    if not (rp.startswith(os.path.realpath(MEM) + "/") or rp.startswith(os.path.realpath(KNOW) + "/") or rp.startswith(os.path.realpath(INBOX) + "/")):
        raise ValueError("outside memory")
    return rp

# ---------------------------------------------------------------- background cache
# Clicks read from memory. Three loops keep memory fresh: git state every 3s, PRs every 60s,
# old conversations every 45s. Writes refresh their own repo synchronously before answering.
LOCK = threading.Lock()
REPO = {}          # (lane, repo) -> {"state","files","log","computed"}
BOARD = {"data": None}
SESS = {}          # repo -> (mtime_signature, text)

def compute_repo(lane, repo):
    try: p = lane_path(lane, repo)
    except ValueError: return None
    st = repo_state(p); fl = files(p) if st.get("exists") else []
    return {"state": st, "files": fl, "log": log(p) if st.get("exists") else [], "path": p, "computed": time.time()}

def all_worktrees():
    out = []
    for f in lane_files():
        w = parse_ws(f"{LANES_DIR}/{f}")
        for r in w["repos"]:
            if os.path.exists(f"{LANES}/{w['id']}/{r['repo']}/.git"): out.append((w["id"], r["repo"]))
    return out

def compute_board():
    sh_ = shorts(); out = []
    for f in lane_files():
        w = parse_ws(f"{LANES_DIR}/{f}")
        for r in w["repos"]:
            p = f"{LANES}/{w['id']}/{r['repo']}"; r["short"] = sh_.get(r["repo"], r["repo"]); r["path"] = p
            c = REPO.get((w["id"], r["repo"]))
            if c and c["state"].get("exists"):
                r.update(c["state"]); fl = c["files"]
                r["staged"] = sum(1 for x in fl if x["staged"]); r["unstaged"] = sum(1 for x in fl if x["unstaged"])
                cached = PR_CACHE.get((p, r.get("branch"))); pr_ = cached[1] if cached else None
                r["pr_failing"] = pr_live_failing(pr_)
                r["pr_state"] = pr_.get("state") if isinstance(pr_, dict) else None
                rebase_target(p, r, pr_, r.get("base"))
            else: r["exists"] = os.path.exists(f"{p}/.git")
        out.append(w)
    order = {"active": 0, "parked": 1}
    out.sort(key=lambda w: (order.get(w["status"], 2), w["id"].lower()))
    return {"lanes": out, "repos": sorted(os.listdir(REPOS)), "generated": time.strftime("%H:%M:%S"), "serverStartedAt": STARTED,
            "tracker": tracker_url()}

def refresh_repo(lane, repo):
    c = compute_repo(lane, repo)
    with LOCK:
        if c: REPO[(lane, repo)] = c
        else: REPO.pop((lane, repo), None)
    return c

def refresh_all():
    live = set(all_worktrees())
    for key in live: refresh_repo(*key)
    with LOCK:
        for key in [k for k in REPO if k not in live]: REPO.pop(key, None)
        BOARD["data"] = compute_board()

def sessions_cached(repo):
    proj = os.path.expanduser("~/.claude/projects/") + f"{REPOS}/{repo}".replace("/", "-").replace("_", "-")
    try: sig = tuple(sorted((e.name, e.stat().st_mtime) for e in os.scandir(proj) if e.name.endswith(".jsonl")))
    except FileNotFoundError: sig = ()
    hit = SESS.get(repo)
    if hit and hit[0] == sig: return hit[1]
    txt = sessions(repo); SESS[repo] = (sig, txt); return txt

def loop(fn, every, name):
    def run():
        while True:
            try: fn()
            except Exception as e: print(f"[{name}] {e}", file=sys.stderr)
            time.sleep(every)
    threading.Thread(target=run, daemon=True, name=name).start()

SELF_MTIME = os.path.getmtime(os.path.realpath(__file__))
def self_reload():
    """Restart when server.py changes on disk, so a running board never serves stale code."""
    if os.path.getmtime(os.path.realpath(__file__)) != SELF_MTIME:
        print("server.py changed — restarting", file=sys.stderr); sys.stderr.flush()
        os.execv(sys.executable, [sys.executable, os.path.realpath(__file__), *sys.argv[1:]])

def pr_sweep():
    for (lane, repo), c in list(REPO.items()):
        st = c["state"]
        if st.get("exists") and st.get("upstream"): pr(c["path"], st.get("branch", ""))
    with LOCK: BOARD["data"] = compute_board()

def sess_sweep():
    for repo in sorted(os.listdir(REPOS)): sessions_cached(repo)

def repo_payload(lane, repo):
    c = REPO.get((lane, repo)) or refresh_repo(lane, repo)
    if not c: raise ValueError("not a lane worktree")
    st = c["state"]; key = (c["path"], st.get("branch", "")); cached = PR_CACHE.get(key)
    pr_ = cached[1] if cached else None
    if cached is None: threading.Thread(target=pr, args=(c["path"], st.get("branch", "")), daemon=True).start()
    sess = SESS.get(repo, (None, None))[1]
    if sess is None: threading.Thread(target=sessions_cached, args=(repo,), daemon=True).start(); sess = ""
    spec_base = None
    try:
        spec_base = next((x.get("base") for x in parse_ws(f"{LANES_DIR}/{lane}.md")["repos"] if x["repo"] == repo), None)
    except Exception: pass
    rebase_target(c["path"], st, pr_, spec_base)
    # both lists share a cap: widening the range must never show fewer commits than narrowing it
    wl = log(c["path"], 60, work_range(c["path"], repo, spec_base)) if st.get("exists") else []
    full = log(c["path"], 60) if st.get("exists") else []
    return {"state": st, "files": c["files"], "log": full or c["log"], "worklog": wl, "pr": pr_, "sessions": sess,
            "nextAction": next_action(st, c["files"], pr_), "computed": c["computed"]}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else (json.dumps(body) if ctype.startswith("application/json") else body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(data)
    def auth(self):
        if self.headers.get("X-Token") != TOKEN: self.send(403, {"error": "bad token"}); return False
        return True
    def q(self):
        return {k: v[0] for k, v in urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).items()}
    def do_GET(self):
        route = urllib.parse.urlparse(self.path).path
        if route == "/":
            html = open(f"{HERE}/index.html").read().replace("__TOKEN__", TOKEN); return self.send(200, html, "text/html")
        if route in STATIC:
            return self.send(200, open(f"{HERE}/{route.lstrip('/')}").read(), STATIC[route])
        if not route.startswith("/api/"): return self.send(404, {"error": "not found"})
        if not self.auth(): return
        q = self.q()
        try:
            if route == "/api/board":
                if BOARD["data"] is None: refresh_all()
                return self.send(200, BOARD["data"])
            if route == "/api/repo": return self.send(200, repo_payload(q["lane"], q["repo"]))
            if route == "/api/show": return self.send(200, show(lane_path(q["lane"], q["repo"]), q.get("sha", ""), q.get("all") == "1"))
            if route == "/api/diff": return self.send(200, diff(lane_path(q["lane"], q["repo"]), q["file"], q.get("staged") == "1", q.get("all") == "1"))
            if route == "/api/memory": return self.send(200, memory_tree())
            if route == "/api/memfile":
                p = mem_path(q.get("scope", ""), q.get("file", ""))
                return self.send(200, {"content": open(p).read() if os.path.exists(p) else "", "path": os.path.relpath(p, AD)})
            if route == "/api/spec":
                f = f"{LANES_DIR}/{q['lane']}.md"; return self.send(200, {"spec": open(f).read() if os.path.exists(f) and re.fullmatch(r"[\w.-]+", q["lane"]) else ""})
            if route == "/api/lanelog":
                whole = q.get("all") == "1"
                return self.send(200, {"log": lane_log(q["lane"], whole=whole), "whole": whole})
            if route == "/api/brief": return self.send(200, {"brief": sh([f"{BIN}/lane-brief", q["lane"]])[1]})
            return self.send(404, {"error": "unknown api"})
        except Exception as e: return self.send(400, {"error": str(e)})
    def do_POST(self):
        route = urllib.parse.urlparse(self.path).path
        if not self.auth(): return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0")) or 0) or b"{}")
            if route == "/api/memory":
                act = body.get("action")
                if act == "move":
                    to = body.get("to", "")
                    args = [f"{BIN}/lane-memory", "move", body.get("file", ""), "cross"] if to == "cross" else [f"{BIN}/lane-memory", "move", body.get("file", ""), "repo", to[5:] if to.startswith("repo:") else to]
                elif act == "rm": args = [f"{BIN}/lane-memory", "rm", body.get("file", "")]
                elif act == "file":
                    sc = body.get("to", ""); slug = (body.get("file", "") or "")[:-3]
                    args = [f"{BIN}/lane-memory", "file", slug] + (["cross"] if sc == "cross" else ["pref"] if sc == "pref" else
                            ["lane", body.get("lane", "")] if sc.startswith("lane") else ["repo", sc[5:] if sc.startswith("repo:") else sc])
                elif act == "drop": args = [f"{BIN}/lane-memory", "drop", (body.get("file", "") or "")[:-3]]
                else: return self.send(400, {"error": "unknown memory action"})
                code, out, err = sh(args, timeout=60)
                return self.send(200 if code == 0 else 400, {"ok": code == 0, "output": (out + err).strip()})
            if route == "/api/ref":
                ws_, act = body.get("lane", ""), body.get("action")
                if not re.fullmatch(r"[A-Za-z0-9._-]+", ws_): return self.send(400, {"error": "bad id"})
                if act == "add":
                    path = os.path.expanduser((body.get("path") or "").strip())
                    if not path: return self.send(400, {"error": "path required"})
                    args = [f"{BIN}/lane-ref", ws_, "add", path] + ([body["note"]] if body.get("note") else []) + (["--rw"] if body.get("rw") else [])
                elif act == "rm": args = [f"{BIN}/lane-ref", ws_, "rm", body.get("name") or body.get("path") or ""]
                elif act == "reveal":
                    target = os.path.realpath(os.path.expanduser(body.get("path") or ""))
                    ok = any(target == os.path.realpath(r["path"]) for r in parse_ws(f"{LANES_DIR}/{ws_}.md")["refs"])
                    if not ok: return self.send(400, {"error": "not a ref of this lane"})
                    subprocess.Popen(["open", "-R", target]); return self.send(200, {"ok": True, "output": "revealed in Finder"})
                else: return self.send(400, {"error": "unknown ref action"})
                code, out, err = sh(args, timeout=60); refresh_all()
                return self.send(200 if code == 0 else 400, {"ok": code == 0, "output": (out + err).strip()})
            if route == "/api/lane":
                code, out, err = run_ws(body.get("action"), body.get("id"), body.get("repos"), body.get("note"))
                return self.send(200 if code == 0 else 400, {"ok": code == 0, "output": (out + err).strip()})
            p = lane_path(body["lane"], body["repo"])
            if route == "/api/pr":
                w = parse_ws(f"{LANES_DIR}/{body['lane']}.md"); base = next((r.get("base") for r in w["repos"] if r["repo"] == body["repo"]), None)
                url = compare_url(p, base); return self.send(200 if url else 400, {"ok": bool(url), "url": url, "output": "" if url else "origin is not a GitHub URL"})
            if route == "/api/discard":
                r = discard(p, body.get("files") or [])
                if "error" in r: return self.send(400, r)
                return self.send(200, r)
            if route == "/api/amend":
                r = amend(p, body.get("message") or "")
                if "error" in r: return self.send(400, r)
                return self.send(200, r)
            if route == "/api/stage":
                fl = [f for f in body.get("files", []) if isinstance(f, str) and not f.startswith("-")]
                if not fl: return self.send(400, {"error": "no files"})
                # The diff of a secret file is withheld, so staging one would commit
                # content nobody could review. Unstaging is always allowed.
                if body.get("stage", True):
                    bad = [f for f in fl if is_secret(f)]
                    if bad:
                        return self.send(400, {"error": "refusing to stage secret file(s): " + ", ".join(sorted(bad))
                                                        + ". Keep them out of git, or add them to .gitignore."})
                code, out, err = sh(["git", "-C", p, "add", "--", *fl]) if body.get("stage", True) else sh(["git", "-C", p, "restore", "--staged", "--", *fl])
            elif route == "/api/commit":
                msg = (body.get("message") or "").strip()
                if not msg: return self.send(400, {"error": "commit message required"})
                staged = git(p, "diff", "--cached", "--name-only")
                if not staged: return self.send(400, {"error": "nothing staged — tick files first"})
                # Belt to the staging brace: a secret can only be staged from outside the
                # board, and it must not become a commit from inside it.
                bad = [f for f in staged.splitlines() if f.strip() and is_secret(f.strip())]
                if bad:
                    return self.send(400, {"error": "refusing to commit secret file(s): " + ", ".join(sorted(bad))
                                                    + ". Unstage them first (git restore --staged)."})
                code, out, err = sh(["git", "-C", p, "commit", "-F", "-"], inp=msg + "\n")
                if code == 0: out = git(p, "log", "-1", "--format=%h %s")
            elif route == "/api/push":
                br = git(p, "branch", "--show-current")
                code, out, err = sh(["git", "-C", p, "push", "-u", "origin", br], timeout=180)
            elif route == "/api/pull":
                code, out, err = sh(["git", "-C", p, "pull", "--ff-only"], timeout=180)
            else: return self.send(404, {"error": "unknown api"})
            refresh_repo(body["lane"], body["repo"])
            if route in ("/api/push", "/api/pull"): PR_CACHE.pop((p, git(p, "branch", "--show-current")), None)
            with LOCK: BOARD["data"] = compute_board()
            return self.send(200 if code == 0 else 400, {"ok": code == 0, "output": (out + err).strip()})
        except Exception as e: return self.send(400, {"error": str(e)})

def main():
    port = PORT
    for attempt in range(20):
        try: ThreadingHTTPServer.allow_reuse_address = True; srv = ThreadingHTTPServer(("127.0.0.1", port), H); break
        except OSError: port += 1
    url = f"http://127.0.0.1:{port}/"
    DEFAULTS.update(defaults())
    refresh_all()
    loop(refresh_all, 3, "git"); loop(pr_sweep, 60, "pr"); loop(sess_sweep, 45, "sessions"); loop(self_reload, 2, "reload")
    print(f"lane-board  {url}   (Ctrl-C to stop)"); sys.stdout.flush()
    if not os.environ.get("WS_BOARD_NO_OPEN"): threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try: srv.serve_forever()
    except KeyboardInterrupt: print("\nstopped")

if __name__ == "__main__": main()
