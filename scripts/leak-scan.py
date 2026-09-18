#!/usr/bin/env python3
"""leak-scan.py <private-control-plane> <folder-to-check>

Checks that nothing identifying from a private control plane appears in a folder you intend to
publish. It does not search for terms someone remembered; it reads the private setup and derives
them: the owner's name, repo names and their short aliases, remote hosts and orgs, the tracker
host, ticket prefixes, lane ids, memory folder names, and the machine's own path segments.

Exit code 0 means nothing was found. Exit 1 lists every hit with the file it is in.

    python3 scripts/leak-scan.py . ../lane
"""
import os, re, sys

COMMON = {
    # ordinary English that shows up inside compound repo names and would drown the report
    "agent", "agents", "api", "app", "back", "backend", "base", "build", "core", "data", "dev",
    "docs", "embed", "end", "export", "front", "harness", "import", "lib", "library", "main",
    "master", "memory", "node", "port", "published", "registry", "repo", "repos", "scripts",
    "server", "service", "site", "tools", "ui", "util", "utils", "web", "work", "worker",
    "github.com", "gitlab.com", "bitbucket.org", "linear.app",
    # tracker and host platforms: shared by everyone, not identifying
    "atlassian", "atlassian.net", "jira", "linear", "azure", "devops",
}

def derive(priv):
    terms = {}
    def add(t, why, split=True):
        t = (t or "").strip().strip("\"'")
        if len(t) < 4 or t.lower() in COMMON or re.fullmatch(r"[\W_]+", t):
            return
        terms.setdefault(t.lower(), why)
        # a compound name also leaks through its distinctive halves, but not its ordinary words
        if split:
            for piece in re.split(r"[-_.]", t):
                if len(piece) >= 5 and piece.lower() not in COMMON:
                    terms.setdefault(piece.lower(), f"part of {why}")

    home = os.path.expanduser("~")
    add(os.path.basename(home), "the unix account name", split=False)
    for seg in os.path.abspath(priv).split("/"):
        if seg and seg not in ("Users", "Desktop", "home"):
            add(seg, "a segment of the private path")

    cfg = os.path.join(priv, "registry", "config.yml")
    if os.path.exists(cfg):
        txt = open(cfg).read()
        m = re.search(r"^\s+name:\s*(.+)$", txt, re.M)
        if m:
            for w in m.group(1).split():
                add(w, "the owner's name", split=False)
        m = re.search(r"^\s+url:\s*(\S+)", txt, re.M)
        if m:
            host = re.sub(r"https?://", "", m.group(1)).split("/")[0]
            add(host, "the tracker host")

    ry = os.path.join(priv, "registry", "repos.yaml")
    if os.path.exists(ry):
        for line in open(ry):
            m = re.match(r"^  ([\w.-]+):\s*$", line)
            if m: add(m.group(1), "a repo name")
            m = re.search(r"^\s+short:\s*(\S+)", line)
            if m: add(m.group(1), "a repo's short alias", split=False)
            m = re.search(r"^\s+origin:\s*(\S+)", line)
            if m:
                u = m.group(1)
                add(re.sub(r"https?://", "", u).split("/")[0], "a remote host", split=False)
                rest = re.sub(r"https?://[^/]+/", "", u).split("/")
                if rest: add(rest[0], "a remote org", split=False)

    wsd = os.path.join(priv, "registry", "lanes")
    for root, _, files in os.walk(wsd):
        for f in files:
            if f.endswith(".md"):
                add(f[:-3], "a lane id")
                m = re.match(r"([A-Z]{2,})-\d+", f)
                if m: add(m.group(1) + "-", "a ticket prefix", split=False)

    for _, dirs, _ in os.walk(os.path.join(priv, "memory")):
        for d in dirs: add(d, "a memory folder name")
        break
    return terms

def scan(target, terms):
    hits = {}
    for root, dirs, files in os.walk(target):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, target)
            try:
                blob = open(p, "rb").read().decode("utf-8", "replace").lower()
            except OSError:
                continue
            hay = blob + "\n" + rel.lower()
            for term, why in terms.items():
                # whole words only: a short term must not match inside a longer word
                pat = re.compile(r"(?<![\w-])" + re.escape(term) + r"(?![\w-])")
                if pat.search(hay):
                    hits.setdefault(term, {"why": why, "files": set()})["files"].add(rel)
    return hits

def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    priv, target = sys.argv[1], sys.argv[2]
    terms = derive(priv)
    hits = scan(target, terms)
    print(f"{len(terms)} identifying terms derived from {priv}")
    print(f"scanned {sum(len(f) for _, _, f in os.walk(target))} files in {target}\n")
    if not hits:
        print("clean — none of them appear")
        return 0
    for term in sorted(hits):
        h = hits[term]
        print(f"LEAK {term!r} ({h['why']})")
        for f in sorted(h["files"])[:5]:
            print(f"       {f}")
    return 1

if __name__ == "__main__":
    sys.exit(main())
