#!/usr/bin/env python3
"""Pull a repository tree into a local directory (github.com is unreachable here).

`scripts/push_tree.py` writes; this reads.  Both compare blob shas instead of
commit history: the remote tree comes from api.github.com, the local side from
git's blob hash of the file content, so the local directory needs no git
repository and a rewritten remote history is harmless.

Usage:
    GITHUB_TOKEN=... python3 scripts/pull_tree.py <dir> <owner/repo> [--branch main] [--prune]

Without --prune, files that exist locally but not remotely are only reported.
"""
import argparse
import base64
import concurrent.futures as cf
import hashlib
import os
import sys

import requests


def blob_sha(path):
    with open(path, "rb") as f:
        data = f.read()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("directory")
    ap.add_argument("repo")
    ap.add_argument("--branch", default="main")
    ap.add_argument("--prune", action="store_true",
                    help="delete local files that no longer exist remotely")
    ap.add_argument("--jobs", type=int, default=12)
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("set GITHUB_TOKEN (or GH_TOKEN)")
    owner, name = args.repo.split("/")
    api = "https://api.github.com/repos/%s/%s" % (owner, name)
    s = requests.Session()
    s.headers.update({"Authorization": "Bearer " + token,
                      "Accept": "application/vnd.github+json"})

    tree = s.get("%s/git/trees/%s?recursive=1" % (api, args.branch), timeout=90).json()
    remote = {e["path"]: e for e in tree.get("tree", []) if e["type"] == "blob"}
    if not remote:
        sys.exit("remote tree empty: %s" % tree.get("message", "?"))

    root = os.path.abspath(args.directory)
    local = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            local[rel] = full

    changed = [p for p in remote
               if p not in local or blob_sha(local[p]) != remote[p]["sha"]]
    extra = [p for p in local if p not in remote]
    print("remote %d files, local %d files" % (len(remote), len(local)))
    print("to fetch/update: %d" % len(changed))
    if extra:
        print("local-only (not in remote): %d" % len(extra))
        for p in sorted(extra)[:20]:
            print("   ", p)

    def fetch(path):
        r = s.get("%s/git/blobs/%s" % (api, remote[path]["sha"]), timeout=120)
        if r.status_code >= 300:
            raise RuntimeError("%s -> %s %s" % (path, r.status_code, r.text[:200]))
        data = base64.b64decode(r.json()["content"])
        full = os.path.join(root, path.replace("/", os.sep))
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(data)
        return path, len(data)

    if changed:
        with cf.ThreadPoolExecutor(args.jobs) as ex:
            for path, size in ex.map(fetch, changed):
                print("  %-64s %8d" % (path, size))

    if args.prune:
        for p in extra:
            os.remove(local[p])
            print("  removed", p)

    print("done: %d file(s) written" % len(changed))


if __name__ == "__main__":
    main()
