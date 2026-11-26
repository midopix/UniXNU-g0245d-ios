#!/usr/bin/env bash
# replay-xnu-work.sh -- reproduce the exact g0245d kernel tree on another machine.
#
# Two ways to land the same bytes, tried in this order:
#
#   1. patches/xnu/g0245d-v384-consolidated.patch
#      One diff of every change we ever made to .cache/xnu-work (120 files).
#      `git apply` it onto a freshly materialised tree and you are done.  This is
#      the path the home machine should normally take.
#
#   2. the incremental scripts/linux/patch_vNNN.py chain
#      Used when the patch cannot apply because the tree already carries part of
#      it (or carries something else in the same hunks).  Every script is
#      idempotent: it looks for its own label and exits early when present.
#
# Either way the result is checked against patches/xnu/g0245d-v384-manifest.sha256.
# "matched 120/120" means the tree is byte-identical to the one that produced
# boot.img md5 e02eab9321120cf10a43d2f8becaae53 (v384).
#
# Usage:
#   XNU_WORK=<tree>/.cache/xnu-work scripts/linux/replay-xnu-work.sh [--from N] [--check-only] [--force]
#
# Env (all optional except XNU_WORK):
#   G0245D_PYTHON     python3 interpreter to use for the incremental scripts
#   G0245D_LAUNCHD    real /sbin/launchd arm64 binary   (scripts v376+)
#   G0245D_DYLD       real /usr/lib/dyld arm64 binary   (script  v383+)
set -uo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
DEV=${G0245D_DEV:-$(cd "$HERE/../.." && pwd)}
PY=${G0245D_PYTHON:-python3}

PATCH=$DEV/patches/xnu/g0245d-v384-consolidated.patch
MANIFEST=$DEV/patches/xnu/g0245d-v384-manifest.sha256

FROM=0
CHECK_ONLY=0
FORCE=0
while [ $# -gt 0 ]; do
    case "$1" in
        --from) FROM=$2; shift 2 ;;
        --check-only) CHECK_ONLY=1; shift ;;
        --force) FORCE=1; shift ;;
        -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
        *) echo "unknown argument: $1" >&2; exit 2 ;;
    esac
done

if [ -z "${XNU_WORK:-}" ]; then
    echo "error: set XNU_WORK to <unixnu out>/.../tree/.cache/xnu-work" >&2
    exit 2
fi
W=$XNU_WORK
if [ ! -f "$W/bsd/kern/kern_exec.c" ] || [ ! -d "$W/.git" ]; then
    echo "error: $W does not look like the xnu work tree (need bsd/kern/kern_exec.c and .git)" >&2
    exit 2
fi
[ -f "$MANIFEST" ] || { echo "error: manifest missing: $MANIFEST" >&2; exit 2; }

manifest_report() {
    local total=0 ok=0 miss=0
    local want path got
    while read -r want path; do
        [ -n "${path:-}" ] || continue
        total=$((total + 1))
        if [ -f "$W/$path" ]; then
            got=$(sha256sum "$W/$path" | cut -d' ' -f1)
            if [ "$got" = "$want" ]; then ok=$((ok + 1)); continue; fi
        fi
        miss=$((miss + 1))
        [ "${VERBOSE:-0}" = 1 ] && echo "    mismatch: $path"
    done < "$MANIFEST"
    echo "manifest: matched $ok/$total (mismatched or missing: $miss)"
    [ "$miss" -eq 0 ]
}

echo "== tree   $W"
echo "== repo   $DEV"
echo
echo "== before"
manifest_report || true
echo

if [ "$CHECK_ONLY" = 1 ]; then
    exit 0
fi

if manifest_report > /dev/null 2>&1 && [ "$FORCE" = 0 ]; then
    echo "== already at v384; nothing to do (use --from N --force to re-run the scripts)"
    exit 0
fi

# ---------------------------------------------------------------- 1. one diff
APPLIED_WITH=none
if [ "$FROM" = 0 ] && [ -f "$PATCH" ]; then
    if git -C "$W" apply --check "$PATCH" 2>/dev/null; then
        echo "== applying consolidated patch ($(du -h "$PATCH" | cut -f1))"
        if git -C "$W" apply --whitespace=nowarn "$PATCH"; then
            APPLIED_WITH=consolidated
        else
            echo "   apply failed after passing --check; falling back to scripts"
        fi
    else
        echo "== consolidated patch does not apply cleanly here; using the script chain"
    fi
fi

# ------------------------------------------------------------- 2. script chain
if [ "$APPLIED_WITH" = none ]; then
    APPLIED_WITH=scripts
    failed=0
    applied=0
    skipped=0
    run=0
    for f in $(ls "$DEV"/scripts/linux/patch_v*.py 2>/dev/null | sort -t v -k2 -n); do
        v=$(basename "$f" | sed 's/patch_v//; s/\.py$//')
        case "$v" in (*[!0-9]*) continue ;; esac
        [ "$v" -ge "$FROM" ] || continue
        run=$((run + 1))
        # v380 taught mockfs about the DEVELOPMENT init path; v381 showed that path
        # overflows the kernel stack and v382 undid it.  Re-running v380 on a tree
        # that already has v382 would silently put the branches back (v382 then
        # sees its own label and skips), so chain them: if v382 is present, skip v380.
        if [ "$v" = 380 ] && grep -q "v382 sp" "$W/osfmk/arm64/sleh.c" 2>/dev/null; then
            echo "skip  v380 (superseded by v382, which is already in the tree)"
            skipped=$((skipped + 1))
            continue
        fi
        # Same story for the container: v376 drops launchd + a 4 KB probe blob into
        # IOKitBSDInit.cpp, v383 swaps the blob for the real dyld, v384 pads the whole
        # thing to v383's size.  The array text only exists in the first step, so
        # replaying v376/v383 after v384 would rewrite the container differently --
        # both are skippable once v384's marker is there.
        if { [ "$v" = 376 ] || [ "$v" = 383 ]; } \
           && grep -q "v384 pad" "$W/iokit/bsddev/IOKitBSDInit.cpp" 2>/dev/null; then
            echo "skip  v$v (container already taken forward by v384)"
            skipped=$((skipped + 1))
            continue
        fi
        if out=$(XNU_WORK="$W" "$PY" "$f" 2>&1); then
            last=$(printf '%s' "$out" | tail -1)
            echo "ok    v$v: $last"
            case "$last" in
                *already*) skipped=$((skipped + 1)) ;;
                *) applied=$((applied + 1)) ;;
            esac
        else
            echo "FAIL  v$v:"
            printf '%s\n' "$out" | tail -4 | sed 's/^/        /'
            failed=$((failed + 1))
        fi
    done
    echo "---- scripts: run=$run applied=$applied skipped=$skipped failed=$failed"
fi

echo
echo "== after ($APPLIED_WITH)"
if manifest_report; then
    echo "== OK: this tree now matches the v384 build that was flashed"
    exit 0
fi
echo "== NOT in sync.  Most common causes, in order:"
echo "   - the tree was built from a different xnu commit (expect xnu-8796.101.5)"
echo "   - a script printed FAIL above (its anchor text moved)"
echo "   - v380/v382 ordering: run again with --from 382, then re-check"
exit 1
