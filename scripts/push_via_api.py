#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把本地 git 仓库相对于某个远程基线的改动，通过 GitHub Git Data API 提交上去。

为什么不用 git push：这台机器上 github.com:443 的 git 端点被阻断（TLS 后被 RST），
只有 api.github.com 可用。API 提交在语义上等价于一次普通提交。

用法：
  GH_TOKEN=... python push_via_api.py <repo_dir> <owner/repo> [--branch main] [--dry-run]
"""
import base64
import json
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
    repo = sys.argv[1]
    full = sys.argv[2]
    branch = "main"
    dry = "--dry-run" in sys.argv
    for i, a in enumerate(sys.argv):
        if a == "--branch":
            branch = sys.argv[i + 1]

    token = os.environ.get("GH_TOKEN")
    if not token:
        sys.exit("GH_TOKEN missing")
    H = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json"}
    S = requests.Session()
    S.headers.update(H)

    head = sh(repo, "rev-parse", "HEAD").strip()

    # 1. 远程 main 当前 head
    r = S.get(f"{API}/repos/{full}/git/ref/heads/{branch}", timeout=30)
    if r.status_code == 404:
        sys.exit(f"branch {branch} not found on {full}")
    r.raise_for_status()
    base_sha = r.json()["object"]["sha"]
    print(f"remote {branch} = {base_sha[:8]}")

    # 2. 本地有没有这个 commit 对象？没有就先 fetch
    if subprocess.run(["git", "-C", repo, "cat-file", "-e", base_sha], capture_output=True).returncode != 0:
        if dry:
            sys.exit("dry-run: local repo lacks remote base commit, cannot diff")
        print("fetching remote base ...")
        subprocess.run(["git", "-C", repo, "fetch", "origin", branch], check=False)
        if subprocess.run(["git", "-C", repo, "cat-file", "-e", base_sha], capture_output=True).returncode != 0:
            sys.exit("still cannot resolve remote base commit locally")

    if base_sha == head:
        print("already up to date")
        return

    # 3. 差异列表
    raw = sh(repo, "diff", "--name-status", "-z", base_sha, head)
    parts = [p for p in raw.split("\0") if p]
    changes = []
    i = 0
    while i < len(parts):
        st = parts[i]
        if st.startswith("R"):
            changes.append((st, parts[i + 2], parts[i + 1]))  # 重命名按 删除+新增 处理
            i += 3
            continue
        changes.append((st[0], parts[i + 1], None))
        i += 2
    print(f"{len(changes)} changed paths")

    # 4. 逐个建 blob
    items = []
    for st, path, old in changes:
        if st == "D":
            items.append({"path": path, "mode": "100644", "type": "blob", "sha": None})
            print("  D", path)
            continue
        blob = sh(repo, "show", f"{head}:{path}", binary=True)
        mode = sh(repo, "ls-tree", head, "--", path).split()[0] if path else "100644"
        if dry:
            print(f"  {st} {path} ({len(blob)} B, would upload)")
            continue
        t = time.time()
        rr = S.post(f"{API}/repos/{full}/git/blobs",
                    json={"content": base64.b64encode(blob).decode(), "encoding": "base64"},
                    timeout=600)
        if rr.status_code >= 300:
            sys.exit(f"blob {path} failed {rr.status_code}: {rr.text[:300]}")
        items.append({"path": path, "mode": mode, "type": "blob", "sha": rr.json()["sha"]})
        print(f"  {st} {path} {len(blob):>7} B  {time.time()-t:.1f}s")
    if dry:
        return

    # 5. tree（基于远程 tree 增量）
    tree = S.post(f"{API}/repos/{full}/git/trees",
                  json={"base_tree": S.get(f"{API}/repos/{full}/git/commits/{base_sha}",
                                           timeout=30).json()["tree"]["sha"],
                        "tree": items}, timeout=300)
    tree.raise_for_status()
    tree_sha = tree.json()["sha"]
    print("tree", tree_sha[:8])

    # 6. commit
    msg = sh(repo, "log", "-1", "--format=%B", head).strip()
    ident = {"name": sh(repo, "config", "user.name").strip() or "midopix",
             "email": sh(repo, "config", "user.email").strip() or "midopix@users.noreply.github.com"}
    when = sh(repo, "log", "-1", "--format=%cI", head).strip()
    c = S.post(f"{API}/repos/{full}/git/commits",
               json={"message": msg, "tree": tree_sha, "parents": [base_sha],
                     "author": {**ident, "date": when}, "committer": {**ident, "date": when}},
               timeout=120)
    c.raise_for_status()
    new_sha = c.json()["sha"]
    print("commit", new_sha[:8])

    # 7. 更新引用（非 force，冲突则报错）
    u = S.patch(f"{API}/repos/{full}/git/refs/heads/{branch}",
                json={"sha": new_sha, "force": False}, timeout=60)
    if u.status_code >= 300:
        sys.exit(f"ref update failed {u.status_code}: {u.text[:300]}")
    print("updated", branch, "->", new_sha[:8])
    print(f"https://github.com/{full}/commit/{new_sha}")


if __name__ == "__main__":
    main()
