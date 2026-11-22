#!/usr/bin/env python3
"""Prune paths from the public repository (github.com is unreachable here).

`scripts/push_tree.py` can add or update blobs but never removes a remote
path -- it compares blob shas of the local tree with the remote tree and
writes what differs.  Deleting therefore needs its own tool, and the GitHub
Trees API is the only way in: post a tree based on the current one with the
unwanted paths set to `sha: null`, commit it and move the branch.

The default list is the progress/handoff material that must stay out of the
public repository.  The single source of truth for the project state is the
private repository's HANDOFF.md.

Usage:
    GITHUB_TOKEN=... python3 scripts/prune_public.py --dry-run
    GITHUB_TOKEN=... python3 scripts/prune_public.py
    GITHUB_TOKEN=... python3 scripts/prune_public.py --path docs/bringup/foo.md
"""
import argparse
import os
import sys

import requests

OWNER = "midopix"
REPO = "UniXNU-g0245d-ios"
API = "https://api.github.com/repos/%s/%s" % (OWNER, REPO)

# Progress reports, handoff notes and per-version reading cards: they belong
# to the private repository, not to the reproducible-artefacts repository.
DEFAULT_PATHS = [
    "docs/bringup/README.md",              # project handoff document
    "docs/bringup/PROGRESS-AND-ROADMAP.md",  # progress snapshot
    "docs/bringup/PUSH-STATUS.md",          # push bookkeeping
    "docs/bringup/PENDING-FLASH-v137.md",   # per-version reading log
    "docs/bringup/MIGRATION-TO-MACOS.md",   # migration bundle note
    "docs/bringup/push-now.sh",             # push helper (private targets)
    "docs/06-ecosystem-scan.md",            # survey of other people's repos
    "docs/bringup/cards/",                  # directory of reading cards
]


def api(session, method, path, **kw):
    r = session.request(method, API + path, timeout=90, **kw)
    if r.status_code >= 300:
        raise SystemExit("%s %s -> %s %s" % (method, path, r.status_code, r.text[:400]))
    return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", action="append", default=[],
                    help="extra path to remove (repeatable); a trailing / removes the tree")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--message", default=None)
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("set GITHUB_TOKEN (or GH_TOKEN)")
    s = requests.Session()
    s.headers.update({"Authorization": "Bearer " + token,
                      "Accept": "application/vnd.github+json"})

    tree = api(s, "GET", "/git/trees/main?recursive=1")
    entries = {e["path"]: e for e in tree.get("tree", []) if e["type"] == "blob"}
    head = api(s, "GET", "/git/ref/heads/main")["object"]["sha"]

    wanted = list(DEFAULT_PATHS) + list(args.path)
    victims = {}
    for w in wanted:
        if w.endswith("/"):
            prefix = w
            for p in entries:
                if p.startswith(prefix):
                    victims[p] = entries[p]
        elif w in entries:
            victims[w] = entries[w]
        else:
            print("  (absent, nothing to prune: %s)" % w)

    if not victims:
        print("nothing to prune")
        return
    print("pruning %d path(s):" % len(victims))
    for p in sorted(victims):
        print("  -", p)
    if args.dry_run:
        print("(dry run; nothing written)")
        return

    deletions = [{"path": p, "mode": victims[p]["mode"], "type": "blob", "sha": None}
                  for p in sorted(victims)]
    new_tree = api(s, "POST", "/git/trees",
                   json={"base_tree": tree["sha"], "tree": deletions})["sha"]
    msg = args.message or ("prune: move progress/handoff documents to the private repository")
    commit = api(s, "POST", "/git/commits",
                 json={"message": msg, "tree": new_tree, "parents": [head]})["sha"]
    api(s, "PATCH", "/git/refs/heads/main", json={"sha": commit, "force": False})
    print("pruned -> commit", commit[:12])


if __name__ == "__main__":
    main()
