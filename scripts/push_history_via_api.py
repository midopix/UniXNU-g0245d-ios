#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 GitHub Git Data API 重放本地历史到远程（用于 filter-branch 之后的 force 更新）。

git push 在本机不可用（github.com:443 被阻断），只能走 api.github.com。
逐 commit 建 blob → tree（base_tree 增量）→ commit，最后一次性 force 更新 ref。

用法：
  GH_TOKEN=... python push_history_via_api.py <repo_dir> <owner/repo> [--branch main] [--root <sha>]
"""
import base64
import os
import subprocess
import sys
import time

import requests

API = "https://api.github.com"


def sh(repo, *args, binary=False):
    out = subprocess.run(["git", "-C", repo, *args], capture_output=True, check=True)
    return out.stdout if binary else out.stdout.decode("utf-8", "replace")


def main():
    repo, full = sys.argv[1], sys.argv[2]
    branch = "main"
    for i, a in enumerate(sys.argv):
        if a == "--branch":
            branch = sys.argv[i + 1]

    tok = os.environ.get("GH_TOKEN") or sys.exit("GH_TOKEN missing")
    S = requests.Session()
    S.headers.update({"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json"})

    commits = sh(repo, "rev-list", "--reverse", "--topo-order", branch).split()
    print(f"{len(commits)} commits to replay")

    parent = None          # 远程上一个 commit sha
    base_tree = None       # 远程上一个 tree sha
    for idx, sha in enumerate(commits):
        meta = sh(repo, "show", "-s", "--format=%an%x00%ae%x00%aI%x00%B", sha).split("\0")
        author_name, author_email, author_date = meta[0], meta[1], meta[2]
        message = meta[3].strip()

        # 这个 commit 相对父 commit 的变化
        if parent is None:
            entries = sh(repo, "ls-tree", "-r", "-z", sha).split("\0")
            changes = []
            for e in entries:
                if not e:
                    continue
                head, path = e.split("\t", 1)
                mode, typ, bsha = head.split()
                changes.append(("A", path, bsha, mode))
        else:
            raw = sh(repo, "diff", "--name-status", "-z", commits[idx - 1], sha)
            parts = [p for p in raw.split("\0") if p]
            changes = []
            i = 0
            while i < len(parts):
                st = parts[i]
                if st[0] in "RC":
                    changes.append(("D", parts[i + 1], None, None))
                    changes.append(("A", parts[i + 2], None, None))
                    i += 3
                else:
                    changes.append((st[0], parts[i + 1], None, None))
                    i += 2

        items = []
        for st, path, bsha, mode in changes:
            if st == "D":
                items.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
                continue
            if bsha is None:
                bsha = sh(repo, "rev-parse", f"{sha}:{path}").strip()
                mode = sh(repo, "ls-tree", sha, "--", path).split()[0]
            body = sh(repo, "cat-file", "blob", bsha, binary=True)
            r = S.post(f"{API}/repos/{full}/git/blobs",
                       json={"content": base64.b64encode(body).decode(), "encoding": "base64"},
                       timeout=600)
            if r.status_code >= 300:
                sys.exit(f"blob {path} @ {sha[:8]} failed {r.status_code}: {r.text[:200]}")
            items.append({"path": path, "mode": mode, "type": "blob", "sha": r.json()["sha"]})

        payload = {"tree": items}
        if base_tree:
            payload["base_tree"] = base_tree
        t = S.post(f"{API}/repos/{full}/git/trees", json=payload, timeout=300)
        if t.status_code >= 300:
            sys.exit(f"tree @ {sha[:8]} failed {t.status_code}: {t.text[:300]}")
        base_tree = t.json()["sha"]

        ident = {"name": author_name, "email": author_email, "date": author_date}
        c = S.post(f"{API}/repos/{full}/git/commits",
                   json={"message": message, "tree": base_tree,
                         "parents": [parent] if parent else [],
                         "author": ident, "committer": ident}, timeout=120)
        if c.status_code >= 300:
            sys.exit(f"commit @ {sha[:8]} failed {c.status_code}: {c.text[:300]}")
        parent = c.json()["sha"]
        print(f"  [{idx+1}/{len(commits)}] {sha[:8]} -> {parent[:8]}  {len(items):>3} paths  {message.splitlines()[0][:52]}")

    u = S.patch(f"{API}/repos/{full}/git/refs/heads/{branch}",
                json={"sha": parent, "force": True}, timeout=60)
    if u.status_code >= 300:
        sys.exit(f"ref update failed {u.status_code}: {u.text[:300]}")
    print(f"forced {branch} -> {parent[:8]}")
    print(f"https://github.com/{full}/commits/{branch}")


if __name__ == "__main__":
    main()
