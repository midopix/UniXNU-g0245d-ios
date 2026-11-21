#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Push a working tree onto a GitHub branch through the Git Data API only.

Unlike push_via_api.py this does not need the remote base commit in the local
object database: it compares the local tree against the *remote* tree by blob
sha and commits the difference on top of the remote head.  That is what makes
it usable here, where the public history was rewritten remotely and the local
clone can no longer share a base with it.

用法：
  GH_TOKEN=... python push_tree.py <dir> <owner/repo> [--branch main] [--dry-run]
"""
import hashlib
import json
import os
import sys

import requests

API = 'https://api.github.com'
SKIP_DIRS = {'.git', '__pycache__', '.venv', 'node_modules'}


def main():
    root = sys.argv[1]
    full = sys.argv[2]
    branch = 'main'
    dry = '--dry-run' in sys.argv
    if '--branch' in sys.argv:
        branch = sys.argv[sys.argv.index('--branch') + 1]
    token = os.environ['GH_TOKEN']
    s = requests.Session()
    s.headers.update({'Authorization': 'Bearer ' + token,
                      'Accept': 'application/vnd.github+json'})

    def api(method, path, **kw):
        r = s.request(method, API + path, timeout=60, **kw)
        if r.status_code >= 300:
            raise SystemExit('%s %s -> %s %s' % (method, path, r.status_code, r.text[:300]))
        return r.json() if r.text.strip() else {}

    head = api('GET', '/repos/%s/git/ref/heads/%s' % (full, branch))
    parent = head['object']['sha']
    base_tree = api('GET', '/repos/%s/commits/%s' % (full, parent))['commit']['tree']['sha']
    remote = {t['path']: t['sha'] for t in
              api('GET', '/repos/%s/git/trees/%s?recursive=1' % (full, base_tree))['tree']
              if t['type'] == 'blob'}
    print('remote %s = %s, %d blobs' % (branch, parent[:10], len(remote)))

    changed = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if fn.endswith('.pyc'):
                continue
            local = os.path.join(dirpath, fn)
            rel = os.path.relpath(local, root).replace('\\', '/')
            data = open(local, 'rb').read()
            blob = hashlib.sha1(b'blob %d\0' % len(data) + data).hexdigest()
            if remote.get(rel) != blob:
                changed.append((rel, local, data, blob))

    print('%d file(s) to write' % len(changed))
    for rel, _l, data, _b in changed:
        print('  %-70s %8d B' % (rel, len(data)))
    if dry or not changed:
        return

    entries = []
    for i, (rel, _l, data, _b) in enumerate(changed, 1):
        if len(data) > 30 * 1024 * 1024:
            print('  skip (>30MB blob limit): %s' % rel)
            continue
        blob = api('POST', '/repos/%s/git/blobs' % full,
                   json={'content': data.decode('utf-8', 'replace') if b'\0' not in data
                         else __import__('base64').b64encode(data).decode(),
                         'encoding': 'utf-8' if b'\0' not in data else 'base64'})
        entries.append({'path': rel, 'mode': '100644', 'type': 'blob', 'sha': blob['sha']})
        print('  [%d/%d] %s' % (i, len(changed), rel))

    tree = api('POST', '/repos/%s/git/trees' % full,
               json={'base_tree': base_tree, 'tree': entries})
    msg = os.environ.get('GH_COMMIT_MSG') or 'v228: text console ladder through arm_init exit'
    commit = api('POST', '/repos/%s/git/commits' % full,
                 json={'message': msg, 'tree': tree['sha'], 'parents': [parent]})
    api('PATCH', '/repos/%s/git/refs/heads/%s' % (full, branch),
        json={'sha': commit['sha'], 'force': False})
    print('pushed %s to %s/%s' % (commit['sha'][:10], full, branch))


if __name__ == '__main__':
    main()
