#!/usr/bin/env python3
"""lane hook dispatcher. Configured in the control plane/.claude/settings.json; runs for every session
launched at the control plane root, including after EnterWorktree moved the session into lanes/<id>/<repo>.
Reads the hook JSON on stdin, decides by hook_event_name. Fails open (exit 0) on unexpected input."""
import fnmatch, json, os, re, subprocess, sys, datetime

AD = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))  # lane, wherever the session was launched


def _owner():
    """Who the messages should name. One line in registry/config.yml. Falls back to a neutral
    word so a fresh clone nobody has configured yet still reads sensibly."""
    try:
        with open(f"{AD}/registry/config.yml") as fh:
            m = re.search(r"^owner:\s*$.*?^\s+name:\s*(.+?)\s*$", fh.read(), re.M | re.S)
            if m:
                return m.group(1).strip().strip("\"'") or "the user"
    except OSError:
        pass
    return "the user"

OWNER = _owner()
REPOS, LANES, LANES_DIR = f"{AD}/repos", f"{AD}/lanes", f"{AD}/registry/lanes"

def out(obj): print(json.dumps(obj).replace("__OWNER__", OWNER)); sys.exit(0)
def deny(event, reason):
    out({"hookSpecificOutput": {"hookEventName": event, "permissionDecision": "deny", "permissionDecisionReason": reason}})
def allow(event): out({"hookSpecificOutput": {"hookEventName": event, "permissionDecision": "allow"}})
def context(event, text): out({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}})
def lane_of(path):
    """lane id if path is under lanes/<id>/…, else None. Only ids that really exist count, so a stray
    path like lanes/repos/… is not reported as a lane."""
    if not path: return None
    p = os.path.realpath(path)
    if not p.startswith(LANES + "/"): return None
    seg = p[len(LANES) + 1:].split("/")[0]
    if not seg: return None
    if os.path.isdir(f"{LANES}/{seg}") or os.path.exists(f"{LANES_DIR}/{seg}.md"): return seg
    return None
def git(cwd, *args):
    try: return subprocess.check_output(["git", "-C", cwd, *args], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception: return ""

def lane_repo_dirs(lane):
    d = f"{LANES}/{lane}"
    return sorted(x for x in os.listdir(d) if os.path.isdir(f"{d}/{x}") and os.path.exists(f"{d}/{x}/.git")) if os.path.isdir(d) else []
def repo_state(path):
    dirty = len([l for l in git(path, "status", "--porcelain").splitlines() if l])
    ahead = git(path, "rev-list", "--count", "@{u}..HEAD") or "no upstream yet"
    behind = git(path, "rev-list", "--count", "HEAD..@{u}") or "-"
    return git(path, "branch", "--show-current"), ahead, behind, dirty
def slug_of(path):
    u = git(path, "remote", "get-url", "origin")
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+)", u or "")
    return m.group(1) if m else ""

def state_block(lane, cwd):
    here = os.path.realpath(cwd); lines = []
    for r in lane_repo_dirs(lane):
        p = f"{LANES}/{lane}/{r}"; b, a, be, d = repo_state(p)
        mark = "*" if here == os.path.realpath(p) or here.startswith(os.path.realpath(p) + "/") else " "
        sl = slug_of(p)
        lines.append(f"  {mark} {r:22} branch: {b:26} ahead: {a:>3}  behind: {be:>3}  uncommitted: {d}"
                     + (f"   [{sl}]" if sl else ""))
    return "\n".join(lines)

SESS_DIR = f"{AD}/.cache/sessions"
def sess_state(sid):
    os.makedirs(SESS_DIR, exist_ok=True); p = f"{SESS_DIR}/{sid or 'nosid'}.json"
    try: return json.load(open(p)), p
    except Exception: return {"mem": [], "rules": []}, p
def sess_save(st, p):
    try: json.dump(st, open(p, "w"))
    except Exception: pass
def read(path, limit=6000):
    try: s = open(path).read()
    except Exception: return ""
    return s if len(s) <= limit else s[:limit] + f"\n… [{len(s)-limit} more chars — open {os.path.relpath(path, AD)} if needed]"
def memory_brief(lane):
    """Cross-repo index + every lane repo's index. Indexes only; Claude opens files it needs."""
    parts = ["MEMORY for this session (indexes; open a linked file when it is relevant):",
             f"## preferences — {AD}/knowledge/preferences.md", read(f"{AD}/knowledge/preferences.md", 3000).strip() or "(empty)",
             f"## cross-repo — {AD}/memory/MEMORY.md", read(f"{AD}/memory/MEMORY.md", 3000).strip()]
    for r in lane_repo_dirs(lane):
        parts += [f"## {r} — {AD}/memory/{r}/MEMORY.md", read(f"{AD}/memory/{r}/MEMORY.md", 3000).strip() or "(empty)"]
    refs = lane_refs(lane)
    if refs:
        parts.append("## references attached to this lane (read-only unless marked rw) — under lanes/%s/refs/:" % lane)
        head = open(f"{LANES_DIR}/{lane}.md").read().split("\n---\n", 1)[0]
        for m in re.finditer(r"^  - path: (.+)\n((?:    .*\n?)*)", head, re.M):
            d = dict(re.findall(r"    (\w+): (.*)", m.group(2)))
            parts.append(f"  - {d.get('name', os.path.basename(m.group(1)))}  [{d.get('mode','read')}]  {m.group(1)}" + (f"  — {d['note']}" if d.get("note") else ""))
    parts.append(SCOPES)
    parts.append("TO SAVE A MEMORY: never write the file yourself. `lane-memory draft <slug>`, write the draft at the path it "
                 "prints, ASK __OWNER__ which scope (recommend one), then `lane-memory file <slug> lane|repo <repo>|cross|pref`. "
                 "The index line is written for you. Findings of this lane are in its spec under ## Findings.")
    return "\n".join(parts)
def rules_brief(lane, repo):
    """The repo's own CLAUDE.md in full plus a list of its rules files, injected the first time a session touches it."""
    root = f"{LANES}/{lane}/{repo}"; out = [f"RULES for {repo} (first touch in this session — they apply to every edit under lanes/{lane}/{repo}/):"]
    for cm in (f"{root}/CLAUDE.md", f"{root}/.claude/CLAUDE.md"):
        if os.path.exists(cm): out += [f"## {os.path.relpath(cm, AD)}", read(cm, 8000).strip()]
    rd = f"{root}/.claude/rules"
    if os.path.isdir(rd):
        out.append(f"## {os.path.relpath(rd, AD)}/ — read the ones that match the files you touch:")
        for f in sorted(os.listdir(rd)):
            if not f.endswith(".md"): continue
            head = read(f"{rd}/{f}", 600)
            m = re.search(r"^description:\s*(.+)$", head, re.M) or re.search(r"^#\s*(.+)$", head, re.M)
            g = re.search(r"^(?:paths|globs):\s*(.+)$", head, re.M)
            out.append(f"  - {f}: {(m.group(1).strip() if m else '')}{('  [applies to: '+g.group(1).strip()+']') if g else ''}")
    if len(out) == 1: out.append("(no CLAUDE.md or rules in this repo)")
    return "\n".join(out)
def repo_of(path, lane):
    if not path or not lane: return None
    rp = os.path.realpath(path); base = os.path.realpath(f"{LANES}/{lane}") + "/"
    if rp.startswith(base):
        seg = rp[len(base):].split("/")[0]
        return seg if os.path.exists(f"{LANES}/{lane}/{seg}/.git") else None
    return None

# ------------------------------------------------------- project rules: registry/rules.yaml
# Every project has refusals that only make sense there — "the entrypoint applies the migrations",
# "that branch deploys itself on push". They do not belong in this file: it is public, and a
# project's tool names, service names and repo names are not. registry/rules.yaml is per-machine
# and gitignored, and what it can say is deliberately small: a rule adds a refusal on top of the
# built-ins. There is no syntax for granting anything — the only thing the code below can do with
# a rule is call deny(), so a rules file can tighten this guard and never loosen it.
RULES_FILE = f"{AD}/registry/rules.yaml"

def _unquote(s):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'": return s[1:-1]
    return s

def _split_out(s, ch):
    """Split on `ch`, ignoring the ones inside quotes — a regex full of punctuation is the norm here."""
    out, buf, q = [], "", ""
    for c in s:
        if q:
            buf += c
            if c == q: q = ""
        elif c in "\"'": q = c; buf += c
        elif c == ch: out.append(buf); buf = ""
        else: buf += c
    out.append(buf)
    return out

def _kv(n, s):
    """`key: value` -> (key, value). value is None for `key:` alone, a dict for a one-line { … }."""
    parts = _split_out(s, ":")
    if len(parts) < 2: raise ValueError(f"line {n}: `{s}` is not `key: value`")
    k, v = parts[0].strip(), ":".join(parts[1:]).strip()
    if not k: raise ValueError(f"line {n}: `{s}` has no key")
    if not v: return k, None
    if v.startswith("{") and v.endswith("}"):
        d = {}
        for piece in _split_out(v[1:-1], ","):
            if not piece.strip(): continue
            pk, pv = _kv(n, piece)
            d[pk] = "" if pv is None else pv
        return k, d
    return k, _unquote(v)

def parse_rules(text):
    """A small YAML subset, on purpose: `rules:` holding a list of maps whose values are scalars,
    one-line flow maps, or a block map indented under the key. Anything else raises ValueError with
    the line number, because a rules file that is half-understood is worse than one that is refused."""
    lines = []
    for n, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"): continue
        lines.append((n, len(raw) - len(raw.lstrip()), raw.strip()))
    if not lines: return []
    if lines[0][1] != 0 or lines[0][2] != "rules:":
        raise ValueError(f"line {lines[0][0]}: the file has to start with `rules:` — nothing else is read from it")
    out, cur, blk, blk_at = [], None, None, -1
    for n, ind, s in lines[1:]:
        if ind == 0:
            raise ValueError(f"line {n}: `{s}` — `rules:` is the only top-level key")
        if s.startswith("- "):
            cur, blk = {}, None; out.append(cur)
            k, v = _kv(n, s[2:].strip()); cur[k] = v
            continue
        if cur is None:
            raise ValueError(f"line {n}: `{s}` is not inside a rule — every rule starts with `- id: <name>`")
        if blk is not None and ind > blk_at:
            k, v = _kv(n, s); blk[k] = "" if v is None else v
            continue
        blk = None
        k, v = _kv(n, s)
        if v is None: blk, blk_at = {}, ind; cur[k] = blk
        else: cur[k] = v
    return out

def load_rules():
    """(rules, complaints). A rule that cannot be trusted is never enforced — and never silent:
    the complaint goes to stderr from the hook and is a failure in `lane doctor`."""
    if not os.path.exists(RULES_FILE): return [], []
    try: text = open(RULES_FILE).read()
    except OSError as e: return [], [f"registry/rules.yaml cannot be read ({e.__class__.__name__})"]
    try: raw = parse_rules(text)
    except ValueError as e: return [], [f"registry/rules.yaml is malformed — {e}"]
    if not isinstance(raw, list): return [], ["registry/rules.yaml: `rules:` has to be a list of rules"]
    good, bad = [], []
    for i, r in enumerate(raw, 1):
        rid = r.get("id") or f"the rule at position {i}"
        w = r.get("when")
        if not isinstance(w, dict) or not w.get("tool"):
            bad.append(f"{rid}: needs `when: {{ tool: <ToolName>, matches|path: … }}`"); continue
        if not w.get("matches") and not w.get("path"):
            bad.append(f"{rid}: `when` needs either `matches:` (a command pattern) or `path:` (a glob)"); continue
        if w.get("matches") and w.get("path"):
            bad.append(f"{rid}: `matches` and `path` in one rule — write two rules, so each refusal says one thing"); continue
        if not r.get("deny"):
            bad.append(f"{rid}: no `deny:` — a rule has to say, in a sentence, what to do instead"); continue
        if not r.get("ref"):
            bad.append(f"{rid}: no `ref:` — a refusal nobody can check is a refusal that gets routed around. "
                       f"Point it at what it is enforcing (memory/…, docs/…, a runbook)."); continue
        if w.get("matches"):
            try: re.compile(w["matches"])
            except re.error as e: bad.append(f"{rid}: `matches` is not a valid regular expression ({e})"); continue
        good.append(r)
    return good, bad

def _path_cands(given, cwd):
    """The forms a `path:` glob may be written against: as typed, absolute, and every tail of the
    absolute path — so `schema/generated/**` matches wherever in a lane the repo is checked out."""
    if not given: return []
    a = abs_of(given, cwd)
    parts = a.strip("/").split("/")
    return [given, given.lstrip("./"), a] + ["/".join(parts[i:]) for i in range(len(parts))]

def rule_hits(rule, tool, ti, segs, cwd):
    w = rule["when"]
    if w["tool"] != tool: return False
    if w.get("matches"):
        # The same normalised segments the built-in command rules are matched against — never a
        # second splitter of our own, or `echo ok && alembic upgrade head` would slip a project
        # rule while the built-ins caught its equivalent.
        pat = re.compile(w["matches"])
        return any(pat.search(s) for s in segs)
    glob = w["path"].strip().rstrip("/")
    pats = [glob] if glob.endswith("*") else [glob, glob + "/**"]
    for key in ("file_path", "notebook_path", "path"):
        for c in _path_cands(ti.get(key) or "", cwd):
            if any(fnmatch.fnmatch(c, p) for p in pats): return True
    return False

def enforce_rules(event, tool, ti, segs, cwd):
    """Runs before the built-ins, because several of them answer `allow` and exit — a project rule
    placed after those would never be reached for the files they cover. It can only ever deny."""
    rules, bad = load_rules()
    if bad:
        print("lane guard: registry/rules.yaml — these project rules are NOT being enforced:\n  "
              + "\n  ".join(bad) + "\n  The built-in rules are unaffected. Fix them, then `lane doctor`.", file=sys.stderr)
    for r in rules:
        try: hit = rule_hits(r, tool, ti, segs, cwd)
        except Exception as e:
            print(f"lane guard: project rule '{r.get('id','?')}' could not be evaluated "
                  f"({e.__class__.__name__}) and was skipped.", file=sys.stderr); continue
        if hit:
            deny(event, f"{r['deny']}\n  This is a project rule of this control plane ('{r['id']}' in "
                        f"registry/rules.yaml), not a built-in one. Why: {r['ref']}")

if "--rules" in sys.argv:
    # `lane doctor` asks the guard itself what it loaded, so the doctor and the hook can never
    # disagree about which rules are in force.
    _rs, _bad = load_rules()
    for _b in _bad: print("!! " + _b, file=sys.stderr)
    print(json.dumps(_rs))
    sys.exit(1 if _bad else 0)

try: data = json.load(sys.stdin)
except Exception: sys.exit(0)
event = data.get("hook_event_name", "")
cwd = data.get("cwd") or os.getcwd()
cur = lane_of(cwd)

# secrets: never read, never edit, never print. Structure is available via `lane-env-keys` and .env.example.
# re.I because most disks are case-insensitive: .ENV, .Env and .env are all the same file.
SECRET_FILE = re.compile(r"(^|/)(\.env(\.[\w.-]+)?|[^/]*\.(pem|key|p12|pfx)|[^/]*credentials[^/]*\.json|secrets?\.(json|ya?ml|toml))$", re.I)
SAFE_ENV_SUFFIX = re.compile(r"\.(example|sample|template|dist)$", re.I)
def is_secret(path):
    if not path: return False
    p = path.rstrip("/")
    if SAFE_ENV_SUFFIX.search(p): return False
    return bool(SECRET_FILE.search(p)) or bool(SECRET_FILE.search(os.path.realpath(p)))
# tokens in a shell command that look like a secret file path
# Commands allowed to name a secret file: they reveal nothing and cannot move it somewhere
# unguarded. Copying and linking are deliberately NOT here — `cp .env /tmp/x && cat /tmp/x`
# is the whole attack. The lane-* scripts that set worktrees up are exempt elsewhere.
SECRET_SAFE_CMD = re.compile(r"""\s*(lane-env-(keys|check)|ls|stat|test|\[|wc|file|touch|mkdir|
    rm|chmod|chown|basename|dirname|readlink|realpath|find)\b""",
    re.X)

ENV_TOKEN = re.compile(r"""(?<![\w-])((?:[\w./~-]*/)?\.env(?:\.[\w.-]+)?|[\w./~-]*credentials[\w.-]*\.json)(?![\w-])|(?:^|[\s'"=])((?:[\w./~-]*/)?[\w-]+\.(?:pem|p12|pfx|key))(?=$|[\s'"])""", re.I)
# verbs that would expose content; anything else mentioning the file (ls, cp, ln, stat, test, wc, mv, readlink, find, du, git) is fine
EXPOSE = re.compile(r"(^|[\s;&|(`])(openssl|cat|head|tail|less|more|bat|sed|awk|grep|egrep|fgrep|rg|ag|ack|cut|sort|uniq|strings|xxd|od|hexdump|python3?|node|deno|bun|ruby|perl|php|jq|yq|source|\.|export|set\s+-a|env|printenv|dotenv|open|code|vim|vi|nano|emacs|tee|xargs|base64|tr|nl|paste|diff|cmp|shasum|md5|scp|rsync|curl|wget|while\s+read)(\s|$)""")
SECRET_MSG = ("Secret file. Claude never reads .env/credential files here, even with permission — the read itself is the problem. "
              "For structure use `lane-env-keys <path>` (names only) or .env.example; for behaviour, run the app and read its output.")

def lane_refs(lane):
    """[(realpath, mode)] from the lane frontmatter refs: list."""
    f = f"{LANES_DIR}/{lane}.md"
    try: head = open(f).read().split("\n---\n", 1)[0]
    except Exception: return []
    out = []
    for m in re.finditer(r"^  - path: (.+)\n((?:    .*\n?)*)", head, re.M):
        mode = re.search(r"^    mode: (\w+)", m.group(2), re.M)
        out.append((os.path.realpath(os.path.expanduser(m.group(1))), mode.group(1) if mode else "read"))
    return out
def ref_name(lane, real):
    """The name a reference is registered under, so messages match what lane-ref expects."""
    f = f"{LANES_DIR}/{lane}.md"
    try: head = open(f).read().split("\n---\n", 1)[0]
    except Exception: return os.path.basename(real)
    for m in re.finditer(r"^  - path: (.+)\n((?:    .*\n?)*)", head, re.M):
        if os.path.realpath(os.path.expanduser(m.group(1))) == real:
            d = dict(re.findall(r"    (\w+): (.*)", m.group(2)))
            return d.get("name", os.path.basename(real))
    return os.path.basename(real)

def ref_mode(path, lane):
    if not path or not lane: return None
    rp = os.path.realpath(path)
    for r, mode in lane_refs(lane):
        if rp == r or rp.startswith(r + "/"): return mode
    return None

def old_paths():
    ps = set()
    try:
        for k in json.load(open(f"{AD}/registry/old-checkouts.json")): ps.add(os.path.realpath(k))
    except Exception: pass
    ps.add(os.path.expanduser("~/.cursor/worktrees"))
    ps.add(os.path.dirname(AD) + "/clones")
    return sorted(ps, key=len, reverse=True)
OLD = old_paths()
def in_old(path):
    if not path: return None
    rp = os.path.realpath(path)
    for o in OLD:
        if rp == o or rp.startswith(o + "/"): return o
    return None
def cmd_mentions_old(cmd):
    for o in OLD:
        short = o.replace(os.path.expanduser("~"), "~")
        if o in cmd or short in cmd: return o
    return None
FROZEN_MSG = ("Frozen copy from before the migration. It is not part of the work any more. Use the worktree under "
              f"{AD}/lanes/ (state: lane-brief). Never read, compare or quote the old checkouts.")

REACH_MSG = ("lanes/{lane}/ belongs to a lane you have not entered. Reaching into it from here is how the "
             "dispatcher ends up editing code it has no scope for.\n"
             "  work on it:   EnterWorktree name=\"{lane}\"\n"
             "  look at it:   `lane-brief {lane}`, `lane-status`, or the board — they read it for you\n"
             "  the lane's own file (registry/lanes/{lane}.md) is editable from here.")

STAY_MSG = ("You are inside lane '{cur}'. The work stays here; do not create or enter another worktree from a worktree. "
            "Need a repo added to THIS work? `lane-add {cur} <repo>`. Is it genuinely separate work __OWNER__ asked for? Then: "
            "`lane-park {cur} \"<note>\"`, ExitWorktree keep, and start it from the root — after they confirm.")

# Memory, preferences and the control plane are never written directly: scope is __OWNER__'s call.
SCOPES = """MEMORY SCOPES — where a thing belongs is decided by how long it stays true:
  preference   knowledge/preferences.md            forever, all work    "how should Claude work with me?"
  cross-repo   memory/<slug>.md                    forever, any repo    "true in every repo?"
  repo         memory/<repo>/<slug>.md             forever, that repo   "still true after this ticket ships?"
  lane         registry/lanes/<id>.md              until it finishes    "only matters while this work is live?"
               (its ## Findings section)                                  then archived with the lane"""
MEMORY_GATE = (
    "Memories are not written directly — the scope is __OWNER__'s decision.\n" + SCOPES + "\n"
    "Do this instead:\n"
    "  1. lane-memory draft <slug>        (prints a path in .cache/memory-inbox/ — write the draft there)\n"
    "  2. ASK __OWNER__ in one line: what it says, and which of the four scopes it is. Recommend one, using the\n"
    "     survival test: does it stay true after this ticket ships? after leaving this repo?\n"
    "  3. lane-memory file <slug> lane | repo <repo> | cross | pref     (files it and writes the index line)")
PLANE_GATE = ("This is the control plane ({what}). Changing it from inside a lane is how the system "
              "drifts. Propose the change to __OWNER__ and make it from a dispatcher session at the control plane root.")

CD_RE = re.compile(r"""(?:^|[;&|]\s*|\bdo\s+|\bthen\s+|\bexec\s+)cd\s+(?:-{1,2}\S+\s+)*("([^"]*)"|'([^']*)'|([^\s;&|)]+))""")
def cd_targets(cmd, cwd):
    """Every directory a Bash command would cd into. In Claude Code a cd moves the session, so a cd is a
    second door into a lane — it has to obey the same rules as EnterWorktree."""
    out = []
    for m in CD_RE.finditer(cmd):
        raw = (m.group(2) or m.group(3) or m.group(4) or "").strip()
        if not raw or raw == "-": continue
        s = raw
        for var in ("$WS_HOME", "${WS_HOME}", "$AD", "${AD}"): s = s.replace(var, AD)
        s = os.path.expanduser(s)
        if "$" in s or "`" in s:
            out.append(("?", raw)); continue           # unresolvable — judge it by what it looks like
        if not os.path.isabs(s): s = os.path.join(cwd, s)
        out.append((os.path.realpath(s), raw))
    return out

HOME = os.path.expanduser("~")
SCRATCH = re.compile(r"^(/private)?/tmp/")
OUTSIDE_MSG = ("Everything you work with lives under the control plane. {what} is outside it.\n"
               "  code of this work      lanes/<lane>/<repo>/\n"
               "  anything else you need attach it once: `lane-ref <lane> add <path> \"why\"`, then read it at\n"
               "                         lanes/<lane>/refs/<name>/… — the reference path, never the real one.\n"
               "  temporary files        the session scratchpad under /tmp")

def abs_of(path, cwd):
    if not path: return ""
    p = os.path.expanduser(path)
    if not os.path.isabs(p): p = os.path.join(cwd, p)
    return os.path.normpath(p)

def outside_ad(given, cwd):
    """The path a tool was pointed at, judged by what was written, not by what a symlink resolves to.
    Returns None when it is fine, or a reason to refuse."""
    if not given: return None
    a = abs_of(given, cwd)
    if a == AD or a.startswith(AD + "/"): return None          # inside the control plane
    if SCRATCH.match(a): return None                            # scratchpad and /tmp
    if not a.startswith(HOME + "/"): return None                # system paths stay readable
    return a

def ref_hint(a, cur):
    """If an outside path is a reference of this lane, point at the reference path instead."""
    if not cur: return ""
    for r, _mode in lane_refs(cur):
        if a == r or a.startswith(r + "/"):
            rel = a[len(r):].lstrip("/")
            return (f"\n  That path IS attached to this lane. Read it at "
                    f"lanes/{cur}/refs/{os.path.basename(r)}/{rel}")
    return ""

def plane_target(rp):
    """What part of the control plane a path belongs to, or None."""
    if not rp.startswith(AD + "/"): return None
    rel = rp[len(AD) + 1:]
    if rel.startswith("memory/") or rel == "memory": return "memory"
    if rel.startswith("knowledge/"): return "knowledge"
    if rel.startswith("registry/lanes/"): return "lane"
    if rel.split("/")[0] in ("scripts", "docs", ".claude") or rel in ("CLAUDE.md", "README.md", "registry/repos.yaml",
                                                                     "registry/old-checkouts.json", "registry/branch-audit.md", ".gitignore"):
        return "plane"
    return None

def write_target_verdict(rp, cur, cwd):
    """Why a write to `rp` is refused, or None. The file tools have judged the control
    plane since the beginning; this is the same judgement for a shell write target, so
    `echo x > guard.py` cannot do what `Write` is refused."""
    if not rp:
        return None
    # A session's own hook config is never writable from inside a session: overwriting it
    # is how a lane switches its own guard off.
    if os.path.basename(rp).startswith("settings") and os.path.basename(os.path.dirname(rp)) == ".claude":
        return ("That file is the session's own permission and hook configuration. Editing it from "
                "inside a session is how the rules get switched off silently. Change it from a "
                "dispatcher session at the control plane root, or ask __OWNER__.")
    kind = plane_target(rp)
    if kind in ("memory", "knowledge"):
        return MEMORY_GATE
    if kind == "lane":
        wid = os.path.basename(rp)[:-3]
        if cur and wid != cur:
            return f"That is lane '{wid}'; this session is in '{cur}'. Only its own spec may be edited from here."
        return None
    if kind == "plane" and cur:
        return PLANE_GATE.format(what=os.path.relpath(rp, AD))
    return None


# ---------------------------------------------------------------- PreToolUse
if event == "PreToolUse":
    tool = data.get("tool_name", "")
    # tool_input is not guaranteed to be an object, and its values are not guaranteed to be
    # strings. A crash here is the worst outcome: the tool runs with no decision at all.
    ti = data.get("tool_input") or {}
    if not isinstance(ti, dict): ti = {}
    ti = {k: (v if isinstance(v, (str, dict, list)) else str(v)) for k, v in ti.items()}
    # A command made only of our own lane-* scripts is the sanctioned way to do things: they validate their own
    # arguments and know the layout. The path rules below are about ad-hoc commands, not about them.
    _c = ti.get("command", "") if tool == "Bash" else ""
    _segs = [s.strip() for s in re.split(r"[;&|]{1,2}|\n", _c) if s.strip()]
    # lane-run / lane-gh carry someone else's command, so they are deliberately NOT exempt: what they run
    # is judged exactly as if it had been typed directly.
    # Only OUR lane-* scripts are trusted: a bare name resolved on PATH, or one under this folder.
    # Anything carrying a path from somewhere else (/tmp/lane-evil) is just another command.
    OURS = bool(_segs) and all(re.match(r"(lane-[\w-]+|(\./)?(scripts|bin)/lane-[\w-]+|"
                                        + re.escape(AD) + r"/(scripts|bin)/lane-[\w-]+)\b", s)
                               and not re.match(r"(\S*/)?lane-(run|gh)\b", s) for s in _segs)
    # Project rules first: they only ever add a refusal, and several built-ins below answer
    # `allow` and exit, which would put the files they cover out of a project rule's reach.
    enforce_rules(event, tool, ti, _segs, cwd)
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        rp0 = os.path.realpath(ti.get("file_path") or ti.get("notebook_path") or "")
        kind = plane_target(rp0)
        if kind in ("memory", "knowledge"):
            # Creating a memory always goes through lane-memory, so the scope is __OWNER__'s choice.
            # Editing one that already exists is allowed from the dispatcher session only: its scope
            # is already settled, and the owner is in the conversation. Worktree sessions are always refused.
            at_root = os.path.realpath(cwd) == os.path.realpath(AD)
            if cur or not at_root or not os.path.exists(rp0):
                deny(event, MEMORY_GATE if not os.path.exists(rp0) or cur else
                     "Editing an existing memory is allowed from a dispatcher session at the control plane root, not from here.")
        if kind == "lane":
            wid = os.path.basename(rp0)[:-3]
            if cur and wid != cur: deny(event, f"That is lane '{wid}'; this session is in '{cur}'. Only its own spec may be edited from here.")
        if kind == "plane" and cur: deny(event, PLANE_GATE.format(what=os.path.relpath(rp0, AD)))
    if tool == "Bash":
        # Judge each segment on its own: our own lane-* scripts are the approved path, even inside a compound command.
        for seg in re.split(r"[;&|]{1,2}|\n", ti.get("command", "")):
            s = seg.strip()
            if not s or re.match(r"(\S*/)?lane-[\w-]+\b", s) or re.match(r"(\S*/)?(scripts|bin)/", s): continue
            if re.search(r"(?:^|[\s'\"])(?:[\w./~-]*/)?(?:memory|knowledge)/[\w./-]+", s) and \
               (re.search(r"(^|[\s])(rm|mv|cp|sed\s+-i|tee|touch)\b", s) or re.search(r">>?\s*\S*(memory|knowledge)/", s)):
                if cur or os.path.realpath(cwd) != os.path.realpath(AD): deny(event, MEMORY_GATE)
    if tool == "EnterWorktree":
        if cur:
            # Which lane is it aiming at? Aiming at its OWN is a re-pin attempt, not an escape.
            aim = lane_of(abs_of(ti.get("path") or "", cwd)) if ti.get("path") else (ti.get("name") or "").strip("/").split("/")[0]
            if aim == cur:
                deny(event, f"You are already in lane {cur}. Nothing is wrong and there is nothing to repair — "
                            f"every repo of {cur} is already reachable from where you stand.\n"
                            f"  a command in a repo:  lane-run <repo> <cmd…>      (mvn, yarn, tests, scripts)\n"
                            f"  GitHub:               lane-gh <repo> <args…>      (pr create, pr checks, workflow run)\n"
                            f"  git:                  git -C <repo> …\n"
                            f"  files:                <repo>/path/to/file       (edit and read them directly)\n"
                            f"If the shell sits inside one repo, that is cosmetic: it changes nothing about what you can "
                            f"reach. Do not try to move it, and do not exit — carry on with the work.")
            deny(event, STAY_MSG.format(cur=cur))
        nm = (ti.get("name") or "").strip("/")
        if ti.get("path"):
            deny(event, "There is one way into a lane: EnterWorktree name=\"<lane-id>\". A path is not "
                        "accepted — it can land outside the registry, in a mirror, or in a stale worktree. "
                        "`lane-status` lists the ids.")
        if not nm:
            deny(event, "EnterWorktree needs name=\"<lane-id>\". `lane-status` lists them.")
        if "/" in nm:
            lane_id = nm.split("/")[0]
            deny(event, f"Name the lane, not a repo: EnterWorktree name=\"{lane_id}\". A session works on every "
                        f"repo of the lane at once — once inside, `cd ../<repo>` switches which one you stand "
                        f"in, and `git -C ../<repo>` needs no move at all. Never exit and re-enter to change repo.")
    if tool == "Bash" and cur:
        c = ti.get("command", "")
        if re.search(r"\bgit\b[^|;&]*\bworktree\s+add\b", c) or re.search(r"(^|[\s;&|/])lane-start(\s|$)", c):
            deny(event, STAY_MSG.format(cur=cur))
        if re.search(r"(^|[\s;&|/])lane-merge(\s|$)", c) and re.search(r"(^|\s)--run(\s|$)", c):
            deny(event, f"A merge moves and removes worktrees, including this one ({cur}). Run it from the "
                        f"control plane root. From here you can only preview it: lane-merge-plan <a> <b> [options].")
        m = re.search(r"(^|[\s;&|/])lane-add\s+(\S+)", c)
        if m and m.group(2) != cur:
            deny(event, f"lane-add targets lane '{m.group(2)}' but you are in '{cur}'. Only `lane-add {cur} <repo>` is allowed from here.")
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Read", "Glob", "Grep"):
        for key in ("file_path", "notebook_path", "path"):
            tp = ti.get(key) or ""
            if not tp: continue
            a = outside_ad(tp, cwd)
            if a: deny(event, OUTSIDE_MSG.format(what=a) + ref_hint(a, cur))
            if not cur:
                lane_t = lane_of(abs_of(tp, cwd))
                if lane_t: deny(event, REACH_MSG.format(lane=lane_t))
            # inside lane: a reference reached through lanes/<id>/refs/ is readable, never writable
            mode = ref_mode(tp, cur) if cur else None
            if mode:
                if tool in ("Read", "Glob", "Grep") or mode == "rw": allow(event)
                deny(event, f"This is a read-only reference of lane '{cur}'. Read it, do not change it. (lane-ref {cur} add <path> --rw to allow edits)")
            if in_old(tp): deny(event, FROZEN_MSG)
    if tool == "Bash" and cur and not OURS:
        c0 = ti.get("command", "")
        for r, mode in lane_refs(cur):
            if mode == "rw": continue
            nm = ref_name(cur, r)
            touched = (r in c0) or (r.replace(HOME, "~") in c0) or (f"refs/{nm}" in c0)
            if touched and (re.search(r"(^|[\s;&|])(rm|mv|sed\s+-i|tee|touch|mkdir|chmod)\b", c0)
                            or re.search(r"\bgit\b[^|;&]*\b(commit|checkout|switch|reset|push|add|rm|mv|stash|rebase|merge|restore|clean)\b", c0)
                            or re.search(r">>?\s*\S*" + re.escape(nm), c0)):
                deny(event, f"'{nm}' is a read-only reference of lane '{cur}': read it, do not change it. "
                            f"(`lane-ref {cur} add <path> --rw` if it should be editable, `lane-ref {cur} rm {nm}` to detach it)")
    if tool == "Bash" and not OURS and cmd_mentions_old(ti.get("command", "")) \
       and not (cur and any(r in ti.get("command", "") for r, _ in lane_refs(cur))):
        deny(event, FROZEN_MSG)
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Read") and is_secret(ti.get("file_path") or ti.get("notebook_path") or ""):
        deny(event, SECRET_MSG)
    if tool == "Bash":
        cmdA = ti.get("command", "")
        # Every path a command names is judged the way a file tool would judge it. Mentioning another
        # lane is refused outright; a mirror is refused only when the path is what the command WRITES.
        # HOME, not a literal /Users/..., because that is macOS-only — this rule silently never
        # fired on Linux (home is /home/<user>) until a real Linux CI run caught it.
        PATH_TOK = re.compile(r"(?<![\w-])((?:~|\$\{?WS_HOME\}?|\$\{?AD\}?|" + re.escape(HOME) + r"|\.{0,2})?/?"
                              r"[\w./-]*(?:lanes|repos)/[\w.-]+[\w./-]*)")
        # A path that climbs out with .. never contains "lanes/" or "repos/", so the pattern above
        # missed it entirely: ../OTHER/file was permitted while its absolute twin was refused.
        # Collect those too and let resolve() turn them into absolute paths for the same checks.
        REL_TOK = re.compile(r"(?<![\w-])(\.\.(?:/[\w.-]+)*/?)")
        PLANE_TOK = re.compile(r"(?<![\w-])(" + re.escape(AD) + r"/[\w./-]+)")
        ALL_TARGETS = re.compile(r"(^|[\s;&|])(rm|touch|mkdir|chmod|dd|truncate|tee)\b|(^|\s)sed\s+-i\b")
        LAST_TARGET = re.compile(r"(^|[\s;&|])(cp|ln|install|rsync)\b")
        # `mv` removes its source as well as writing its destination, so both ends count.
        MOVE_TARGETS = re.compile(r"(^|[\s;&|])mv\b")
        def resolve(raw):
            s = raw
            for v in ("${WS_HOME}", "$WS_HOME", "${AD}", "$AD"): s = s.replace(v, AD)
            return abs_of(s.replace("~", HOME), cwd)
        if not OURS:
            for seg in [s for s in re.split(r"[;&|]{1,2}|\n", cmdA) if s.strip()]:
                toks = [m.group(1) for m in PATH_TOK.finditer(seg)]
                toks += [m.group(1) for m in REL_TOK.finditer(seg)]
                # PATH_TOK only matches paths that contain lanes/ or repos/, so an
                # absolute path to the control plane's own files — scripts/, CLAUDE.md,
                # .claude/ — was never collected and therefore never judged.
                toks += [m.group(1) for m in PLANE_TOK.finditer(seg)]
                if not toks: continue
                paths = [resolve(x) for x in toks]
                # another lane: any mention at all
                for a in paths:
                    lane_t = lane_of(a)
                    if lane_t and lane_t != cur:
                        deny(event, REACH_MSG.format(lane=lane_t) if not cur else STAY_MSG.format(cur=cur))
                # a mirror: only when it is written to
                targets = []
                if ALL_TARGETS.search(seg) or MOVE_TARGETS.search(seg): targets = paths
                elif LAST_TARGET.search(seg):
                    # cp/mv/ln write to their LAST argument; everything before it is a source and may be read.
                    args = [x.strip("\"'") for x in seg.split() if not x.startswith("-")]
                    targets = [resolve(args[-1])] if len(args) > 1 else []
                elif re.search(r"\bgit\b[^|;&]*\b(commit|checkout|switch|reset|push|add|rm|mv|stash|rebase|merge|"
                               r"restore|clean|apply|am|cherry-pick|branch|tag|worktree)\b", seg):
                    m = re.search(r"-C\s+(\S+)", seg)
                    targets = [resolve(m.group(1))] if m else paths
                for m in re.finditer(r">>?\s*(\S+)", seg): targets.append(resolve(m.group(1)))
                for a in targets:
                    if a == REPOS or a.startswith(REPOS + "/"):
                        deny(event, f"{os.path.relpath(a, AD)} is inside a read-only mirror. Mirrors stay on the "
                                    f"default branch and clean; work happens in a lane. Reading them is fine.")
                    reason = write_target_verdict(a, cur, cwd)
                    if reason: deny(event, reason)
        if not OURS:
            # any absolute path under $HOME that is not inside lane. HOME, not /Users/..., for
            # the same reason as PATH_TOK above — this whole check was a no-op on Linux.
            for m in re.finditer(r"(?<![\w-])((?:~|" + re.escape(HOME) + r")/[^\s\"';|&)]+)", cmdA):
                raw = m.group(1)
                a = outside_ad(raw, cwd)
                if a: deny(event, OUTSIDE_MSG.format(what=a) + ref_hint(a, cur))
            # and any path that climbs out with .. — the absolute form was refused while the
            # relative one was not, which made the rule a formality
            for m in re.finditer(r"(?<![\w-])(\.\.(?:/[\w.-]+)*/?)", cmdA):
                a = outside_ad(m.group(1), cwd)
                if a: deny(event, OUTSIDE_MSG.format(what=a) + ref_hint(a, cur))
        # gh reaches the same repositories over the network. Only the irreversible ones are refused here.
        if re.search(r"\bgh\b[^|;&]*\brepo\b[^|;&]*\b(delete|archive|rename|transfer)\b", cmdA):
            deny(event, "Deleting, archiving, renaming or transferring a repository is never part of the work.")
        if re.search(r"\bgh\b[^|;&]*\bapi\b[^|;&]*(-X|--method)\s*(DELETE|PUT|PATCH)\b", cmdA):
            deny(event, "A writing gh api call (DELETE/PUT/PATCH) bypasses every check we have. Say what you need "
                        "and let __OWNER__ decide; read-only `gh api` is fine.")
        # the remote and the default branches are not Claude's to change
        if re.search(r"\bgit\b[^|;&]*\bremote\b[^|;&]*\b(add|set-url|remove|rm|rename|prune)\b", cmdA) \
           or re.search(r"\bgit\b[^|;&]*\bconfig\b[^|;&]*\bremote\.[\w.-]+\.(url|pushurl)\b", cmdA):
            deny(event, "Changing a git remote is never part of the work. If origin looks wrong, say so and stop.")
        if re.search(r"\bgit\b[^|;&]*\b(symbolic-ref|update-ref)\b[^|;&]*\brefs/heads/(main|master|develop)\b", cmdA) or \
           re.search(r"\bgit\b[^|;&]*\bbranch\b[^|;&]*\s-[DfM]\b[^|;&]*\b(main|master|develop)\b", cmdA):
            deny(event, "Moving or deleting a default branch (main/master/develop) is not something to do unasked.")
        if re.search(r"\bgit\b[^|;&]*\bpush\b", cmdA) \
           and re.search(r"(:|\s)(refs/heads/)?(main|master|develop)(\s|$)", cmdA) \
           and not cmdA.lstrip().startswith("ALLOW_DEFAULT_BRANCH_PUSH=1"):
            deny(event, "That pushes to a default branch (main/master/develop). Ask __OWNER__ first. If they agree, run it "
                        "with the marker they can see: ALLOW_DEFAULT_BRANCH_PUSH=1 git push …")
        STAY_PUT = ("A cd moves the session itself, and once you are out of lane '{cur}' the way back is "
                    "EnterWorktree, not cd — so a single cd for convenience strands the session.\n"
                    "  lane-* scripts run from anywhere: `lane-status`, `lane-brief {cur}`, `lane-memory …` — no cd needed\n"
                    "  another repo of this lane: `git -C ../<repo> …`, or absolute paths for file tools\n"
                    "  a temporary file: write it by absolute path under /tmp")
        for tgt, raw in cd_targets(cmdA, cwd):
            if tgt == "?":
                if cur or "/lanes/" in raw or "/repos/" in raw:
                    deny(event, STAY_PUT.format(cur=cur) if cur else
                         "Do not cd into a worktree or a mirror. A cd moves the session without resuming the "
                         "lane or applying its scope. Use EnterWorktree name=\"<lane-id>\".")
                continue
            if cur:
                mine = os.path.realpath(f"{LANES}/{cur}")
                if not (tgt == mine or tgt.startswith(mine + "/")):
                    deny(event, STAY_PUT.format(cur=cur))          # leaving the lane entirely
                # Inside the lane: the session lives at its root. Entering a repo is what made one of
                # them look like the main one, and nothing needs it any more — lane-run does the moving.
                tgt_repo = repo_of(tgt, cur)
                here_repo = repo_of(cwd, cur)
                if tgt_repo and tgt_repo != here_repo:
                    deny(event, f"Stay in the lane — do not cd into {tgt_repo}. Anything that must run inside a "
                                f"repo runs there without moving the session:\n"
                                f"  a command:  lane-run {tgt_repo} <cmd…>        (mvn, yarn, tests, scripts)\n"
                                f"  GitHub:     lane-gh {tgt_repo} <args…>        (pr create, pr checks, workflow run)\n"
                                f"  git:        git -C {tgt_repo} …\n"
                                f"  files:      {tgt_repo}/path/to/file         (edit and read them directly)")
                continue
            if tgt == REPOS or tgt.startswith(REPOS + "/"):
                deny(event, f"{os.path.relpath(tgt, AD)} is a read-only mirror; do not cd into it. Work happens in a "
                            f"lane: EnterWorktree name=\"<id>\". Read it in place with `git -C` or absolute paths.")
            lane_t = lane_of(tgt)
            if lane_t:
                deny(event, f"Do not cd into a lane — that skips the resume and the scope that come with it. "
                            f"Use EnterWorktree name=\"{lane_t}\" instead.")

    if tool == "Bash" and cur:
        m = re.search(re.escape(f"{LANES}/{cur}/") + r"([\w.-]+)", ti.get("command", "")) or re.search(r"(?:^|\s)(?:cd|-C)\s+(?:\S*/)?lanes/" + re.escape(cur) + r"/([\w.-]+)", ti.get("command", ""))
        repo = m.group(1) if m and os.path.exists(f"{LANES}/{cur}/{m.group(1)}/.git") else None
        if repo:
            st, sp = sess_state(data.get("session_id", ""))
            if repo not in st["rules"]:
                st["rules"].append(repo); sess_save(st, sp)
                out({"hookSpecificOutput": {"hookEventName": event, "additionalContext": rules_brief(cur, repo)}})
    if tool == "Bash":
        cmd0 = ti.get("command", "")
        toks = [(m.group(1) or m.group(2)) for m in ENV_TOKEN.finditer(cmd0) if not SAFE_ENV_SUFFIX.search(m.group(1) or m.group(2))]
        # Deny by default. Listing the readers meant `dd`, `gpg -d`, `git show HEAD:.env` and
        # anything else unlisted got straight through. These few only touch metadata or move
        # the file; everything else that names a secret is refused.
        # a command is a chain; check each part that names a secret, not just the first word
        parts = [s for s in re.split(r"&&|\|\||[;|\n]", cmd0) if ENV_TOKEN.search(s)]
        unsafe = [s for s in parts if not SECRET_SAFE_CMD.match(s)]
        if toks and (unsafe or not parts):
            deny(event, SECRET_MSG + f" (command references {', '.join(sorted(set(toks)))})")
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Read"):
        fp = ti.get("file_path") or ti.get("notebook_path") or ""
        rp = os.path.realpath(fp) if fp else ""
        if rp.startswith(REPOS + "/") and (tool != "Read" or cur):
            deny(event, f"{AD}/repos/ is the read-only mirror. Work in the lane worktree under lanes/ (scripts/lane-start or lane-resume).")
        target = lane_of(rp)
        if cur and target and target != cur:
            deny(event, f"'{target}' is a different lane. This session is in '{cur}'. Ask __OWNER__ to add that repo with scripts/lane-add {cur} <repo>, or switch lanes.")
        if cur and target == cur:
            repo = repo_of(rp, cur); extra = None
            here = repo_of(cwd, cur)  # the repo the session stands in loads its own CLAUDE.md natively
            if repo and repo != here:
                st, sp = sess_state(data.get("session_id", ""))
                if repo not in st["rules"]:
                    st["rules"].append(repo); sess_save(st, sp); extra = rules_brief(cur, repo)
            o = {"hookSpecificOutput": {"hookEventName": event, "permissionDecision": "allow"}}
            if extra: o["hookSpecificOutput"]["additionalContext"] = extra
            out(o)
        sys.exit(0)
    if tool == "Bash":
        cmd = ti.get("command", "")
        in_mirror = (os.path.realpath(cwd).startswith(REPOS + "/")
                     or re.search(re.escape(REPOS) + r"/[\w.-]+", cmd) is not None
                     or re.search(r"(^|[;&|]\s*)cd\s+\S*/?repos/", cmd) is not None)
        if in_mirror and re.search(r"\bgit\b[^|;&]*\b(checkout|switch|reset|commit|merge|rebase|stash|cherry-pick|am|apply|clean|restore|push)\b", cmd) \
           and not re.search(r"\bgit\b[^|;&]*\bworktree\b", cmd):
            deny(event, "The mirrors under repos/ stay on the default branch and clean. Only fetch/pull --ff-only/log/status/worktree are allowed there. Use scripts/lane-* for work.")
        if re.search(r"\bgit\s+stash(\s+(pop|apply|drop))?\s*($|[;&|])", cmd) or re.search(r"\bgit\s+stash\s+pop\b", cmd):
            deny(event, "Bare git stash/pop is unsafe here: the stash stack is shared across worktrees. Make a wip commit instead (scripts/lane-park does this).")
        if re.search(r"\bgit\s+push\b.*(\s-f\b|--force\b)", cmd) and re.search(r"\b(master|main|develop)\b", cmd):
            deny(event, "Force-pushing a default/integration branch is blocked. Ask __OWNER__ explicitly if this is really intended.")
        if re.search(r"\brm\s+(-\w*r\w*\s+)+\S*(" + re.escape(REPOS) + "|" + re.escape(LANES) + r")(/|\s|$)", cmd):
            deny(event, "Deleting mirrors or worktrees by hand is blocked. Use scripts/lane-done (worktrees) or ask __OWNER__ (mirrors).")
    sys.exit(0)

# ------------------------------------------------------------ PostToolUse: touched files
if event == "PostToolUse":
    tool = data.get("tool_name", "")
    # tool_input is not guaranteed to be an object, and its values are not guaranteed to be
    # strings. A crash here is the worst outcome: the tool runs with no decision at all.
    ti = data.get("tool_input") or {}
    if not isinstance(ti, dict): ti = {}
    ti = {k: (v if isinstance(v, (str, dict, list)) else str(v)) for k, v in ti.items()}
    if cur and tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        fp = ti.get("file_path") or ti.get("notebook_path")
        if fp:
            with open(f"{LANES}/{cur}/.touched", "a") as f: f.write(os.path.realpath(fp) + "\n")
    sys.exit(0)

# --------------------------------------------------------- UserPromptSubmit: one-line state
if event == "UserPromptSubmit":
    if cur:
        rel = os.path.relpath(os.path.realpath(cwd), AD)
        st, sp = sess_state(data.get("session_id", "")); pre = ""
        if cur not in st["mem"]:
            st["mem"].append(cur); sess_save(st, sp); pre = memory_brief(cur) + "\n\n"
        repos_here = lane_repo_dirs(cur)
        at_root = os.path.realpath(cwd) == os.path.realpath(f"{LANES}/{cur}")
        how = ""
        if len(repos_here) > 1:
            where = ("You are in the lane itself, which is the normal place to sit — no repo is home."
                     if at_root else
                     "The shell sits inside one repo — an older session lands that way. It says nothing about "
                     "which repo matters and it costs you nothing: every repo below is reachable from here by the "
                     "four routes above. Leave it alone. Do not cd, do not exit, do not re-enter — there is "
                     "nothing to repair, and the attempt just burns turns.")
            how = (f"\nAll {len(repos_here)} repos above are yours to work on right now — this is one piece of work, "
                   f"not one repo. {where}\n"
                   f"  edit any repo:    <repo>/… under lanes/{cur}/ (absolute paths work from anywhere in it)\n"
                   f"  git in a repo:    git -C <repo> …\n"
                   f"  run anything in a repo:  lane-run <repo> <cmd…>   ·   GitHub: lane-gh <repo> <args…>\n"
                   f"  do NOT cd into a repo — you never need to, and the hook refuses it\n"
                   f"  NEVER ExitWorktree/EnterWorktree to change repo — a cd does it and keeps the lane.")
        context(event, pre + f"STATE of lane {cur} (every repo in it; * = where you are: {rel}). Report state only in this form:\n"
                       + state_block(cur, cwd) + how +
                       f"\nSpec: registry/lanes/{cur}.md. Never mention repos/ or the old checkouts.")
    if os.path.realpath(cwd) == os.path.realpath(AD):
        context(event, "[lane] at the dispatcher root, no lane entered. If this request is code work on a repo, first offer/enter a lane (EnterWorktree) and say so; do not edit code from here.")
    sys.exit(0)

# --------------------------------------------------------------- PreCompact: keep the spec
if event == "PreCompact":
    if cur and os.path.exists(f"{LANES_DIR}/{cur}.md"):
        spec = open(f"{LANES_DIR}/{cur}.md").read()
        context(event, ("Preserve through compaction — the session is in lane '%s' at %s.\n"
                        "Rules that still apply after this compaction:\n"
                        "  - the only way into a lane is EnterWorktree name=\"<id>\"; never cd into one\n"
                        "  - work only under lanes/%s/; repos/ are read-only mirrors; other lanes are out of bounds\n"
                        "  - nothing outside the control plane is readable; attach it with lane-ref and read it under refs/\n"
                        "  - never change a git remote, never move a default branch, ask before any commit or a push to main\n"
                        "  - memories go through lane-memory; __OWNER__ chooses the scope\n"
                        "  - old checkout paths in earlier turns are frozen copies; they all mean this worktree now\n"
                        "Its spec:\n%s") % (cur, cwd, cur, spec))
    sys.exit(0)

# --------------------------------------------------------------- SessionEnd: auto-log
if event == "SessionEnd":
    try: os.remove(f"{SESS_DIR}/{data.get('session_id','')}.json")
    except Exception: pass
    # Keep every transcript in exactly one project folder, under its repo. A conversation resumed from the
    # lane root may get its continuation written under the root's project folder; if the same id also
    # exists under a repos/<repo> folder, move the newer file into the repo folder and park the older one.
    sid = data.get("session_id", "")
    proj = os.path.expanduser("~/.claude/projects")
    root_slug = AD.replace("/", "-").replace("_", "-")
    root_f = f"{proj}/{root_slug}/{sid}.jsonl"
    if sid and os.path.exists(root_f):
        import glob as _g
        others = _g.glob(f"{proj}/{root_slug}-repos-*/{sid}.jsonl")
        if len(others) == 1:
            repo_f = others[0]
            newer, older = (root_f, repo_f) if os.path.getmtime(root_f) >= os.path.getmtime(repo_f) else (repo_f, root_f)
            os.replace(older, older + ".superseded")
            if newer == root_f: os.replace(root_f, repo_f)
            with open(f"{AD}/.cache/transcript-moves.log", "a") as lg:
                lg.write(f"{datetime.datetime.now():%F %T} {sid}: kept newest under {os.path.dirname(repo_f)}; older -> .superseded\n")
    if cur and os.path.exists(f"{LANES_DIR}/{cur}.md"):
        touched = set()
        tf = f"{LANES}/{cur}/.touched"
        if os.path.exists(tf):
            touched = {os.path.relpath(l.strip(), f"{LANES}/{cur}") for l in open(tf) if l.strip()}; os.remove(tf)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        parts = []; any_dirty = False
        for r in lane_repo_dirs(cur):
            b, a, be, d = repo_state(f"{LANES}/{cur}/{r}"); any_dirty |= d > 0
            parts.append(f"{r}@{b} ahead {a} behind {be} dirty {d}")
        line = f"- {now} session ended: " + "; ".join(parts)
        if touched: line += "; touched " + ", ".join(sorted(touched)[:12]) + (" …" if len(touched) > 12 else "")
        if any_dirty: line += " — UNPARKED: uncommitted work left in a worktree"
        with open(f"{LANES_DIR}/{cur}.md", "a") as f: f.write(line + "\n")
        # Rewrite `updated:` in place. Done in python because `sed -i` needs an argument on BSD
        # and refuses one on GNU, and this runs on both.
        try:
            sp = f"{LANES_DIR}/{cur}.md"
            txt = re.sub(r"^updated: .*$", f"updated: {now[:10]}", open(sp).read(), count=1, flags=re.M)
            open(sp, "w").write(txt)
        except OSError:
            pass
    sys.exit(0)

if event == "SessionStart" and data.get("source") == "compact":
    # the session lost its context; let the memory brief and the per-repo rules be injected again
    try: os.remove(f"{SESS_DIR}/{data.get('session_id','')}.json")
    except Exception: pass
    sys.exit(0)

# ------------------------------------------------- WorktreeCreate: EnterWorktree(name="<id>/<repo>")
if event == "WorktreeCreate":
    if cur:
        print(STAY_MSG.format(cur=cur), file=sys.stderr); sys.exit(1)
    # EnterWorktree name= is interpreted by us, not by git:
    #   "<id>"          an existing lane -> resume it and land in whichever repo the work is in
    #   "<id>/<repo>"   that repo of that lane; creates the lane/worktree if needed
    name = data.get("name", "").strip("/")
    parts = [x for x in name.split("/") if x]
    known = sorted(os.listdir(REPOS))

    def repos_in(lane_id):
        f = f"{LANES_DIR}/{lane_id}.md"
        if not os.path.exists(f): return []
        head = open(f).read().split("\n---\n", 1)[0]
        return re.findall(r"^  - repo: (\S+)$", head, re.M)

    if len(parts) == 1:
        lane_id = parts[0]
        rs = repos_in(lane_id)
        if not rs:
            active = sorted(os.path.basename(f)[:-3] for f in __import__("glob").glob(f"{LANES_DIR}/*.md"))
            print(f"lane: no lane '{lane_id}'. To start new work name a repo too: <id>/<repo>.\n"
                  f"  repos: {', '.join(known)}\n  lanes: {', '.join(active)}", file=sys.stderr)
            sys.exit(1)
        r = subprocess.run([f"{AD}/scripts/lane-resume", lane_id], capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout + r.stderr, file=sys.stderr); sys.exit(1)
        live = [x for x in rs if os.path.exists(f"{LANES}/{lane_id}/{x}/.git")]
        if not live:
            print(f"lane: lane '{lane_id}' has no worktree to enter", file=sys.stderr); sys.exit(1)
        # Sit in the lane itself, not in one of its repos. The anchor repo in that folder is what
        # makes it possible; without it git would resolve the folder to lane and Claude Code would refuse.
        if os.path.exists(f"{LANES}/{lane_id}/.git"):
            print(f"lane: in lane {lane_id}. Its repos — {', '.join(live)} — are all yours to work on; "
                  f"none is primary. Edit them at <repo>/…, run git with `git -C <repo>`, and `cd <repo>` only when a "
                  f"tool needs the working directory.", file=sys.stderr)
            print(f"{LANES}/{lane_id}"); sys.exit(0)
        # No repo of a lane is primary. A session has to start somewhere, so start where the work is:
        # uncommitted changes first, then the most recent commit. The choice changes with the work, by design.
        def recency(x):
            d = f"{LANES}/{lane_id}/{x}"
            dirty = len([l for l in git(d, "status", "--porcelain").splitlines() if l])
            when = git(d, "log", "-1", "--format=%ct") or "0"
            return (-min(dirty, 1), -int(when) if when.isdigit() else 0, x)
        here = sorted(live, key=recency)[0]
        if len(live) > 1:
            rest = [x for x in live if x != here]
            print(f"lane: a session's folder is always one repo — git needs it — so this one starts in {here}, "
                  f"where the most recent work is. That makes it no more important than {', '.join(rest)}.\n"
                  f"  to work in another repo of {lane_id}:   cd ../<repo>      (allowed, and it stays in the lane)\n"
                  f"  to start there next time:             EnterWorktree name=\"{lane_id}/<repo>\"\n"
                  f"  never exit and re-enter to switch repo — that is what a cd is for.", file=sys.stderr)
        print(f"{LANES}/{lane_id}/{here}"); sys.exit(0)

    lane_id = parts[0]
    print(f"lane: name the lane, not a repo — EnterWorktree name=\"{lane_id}\". A session works on every "
          f"repo of the lane at once; `cd ../<repo>` switches which one you stand in. A lane is created "
          f"with `lane-start {lane_id} <repo>[:<branch>][@<base>] …`.", file=sys.stderr); sys.exit(1)

if event == "WorktreeRemove":
    print("lane: worktrees are removed by scripts/lane-done after the branch is pushed. Nothing was removed.", file=sys.stderr); sys.exit(1)

sys.exit(0)
