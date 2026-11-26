#!/usr/bin/env python3
"""Fix the duplicated `} }` left by patch_v389.py's broken-variant repair."""
import sys

SLEH = "/home/myth/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work/osfmk/arm64/sleh.c"
src = open(SLEH, encoding="utf-8").read()

DUP = (
    "\t  } }\n"
    "\n"
    "\t  } }\n"
    "\n"
    "\t/* g0245d v389"
)
FIX = (
    "\t  } }\n"
    "\n"
    "\t/* g0245d v389"
)
if DUP in src:
    src = src.replace(DUP, FIX, 1)
    open(SLEH, "w", encoding="utf-8").write(src)
    print("v389: duplicated closing brace removed")
elif src.count(DUP) == 0 and FIX in src:
    print("v389: already clean")
else:
    sys.exit("v389-fix: unexpected sleh.c state")
