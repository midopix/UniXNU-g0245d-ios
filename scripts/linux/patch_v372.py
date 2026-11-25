#!/usr/bin/env python3
"""patch_v372 -- stop flushing the whole text area on every console line.

Why (v371 photo evidence, 2026-11-25 15:03:49):
  ring tail: 10618 v353 asid / 10619 v353 tte / 10620 v353 is64 /
             10621 v354 ttep low / 10622 v356 spmap / dim 10623 v371 lr
  hb307 10623/10580 v371 lr
  status: >v366 pre switch

  The build only differs from v370 by three extra trace lines in
  pmap_switch, yet the freeze moved EARLIER (v370 stopped after
  "v356 pre", v371 stops after "v371 lr").  A fixed code defect cannot move
  backwards when probes are added, so the stop point is not a specific
  instruction -- it is whatever line happened to be printing when something
  timed out.

  osfmk/arm/arm_init.c:g0245d_con_sync() is the suspect:
      end = base + rows * CH * stride;
      for (p = base; p < end; p += 64)  dc civac, p
      dsb sy
  i.e. the WHOLE text area (~1 MB) is clean+invalidated for EVERY traced
  line -- ~15k maintenance ops + a full DSB per line, >150M ops by seq 10623.
  `tlbi vmalle1` already proved this SoC hangs intermittently on maintenance
  ops of exactly that class (v365 workaround, §14.22).  Cheap ops that only
  ever take a couple of ms are also why the ring wrap looks like "only six
  lines on screen": on wrap the ring blanks itself, so a photo taken just
  after a wrap shows few rows.

  Note the console also needs only "clean": the display scans DRAM, so
  `civac` buys nothing and can throw away dirty lines.

Change (osfmk/arm/arm_init.c only, no pmap changes):
  * track the row range painted since the last flush (g0245d_con_dlo/dhi,
    updated in g0245d_con_px, which every glyph/blank write funnels through)
  * g0245d_con_sync(): flush only [dlo, dhi] with `dc cvac` + `dsb sy`
    => ~40x fewer maintenance ops per line, and never invalidate.

Reading the next photo:
  * if the run gets much further / the freeze disappears -> maintenance
    storm on the console path was the blocker; keep the bounded flush
  * if it still stops right after a trace line -> console maintenance is
    exonerated, next suspect is the exception path (silent EL1 abort)
  * screen must still scroll normally; a blank screen would mean the flush
    range is wrong (then switch back to `civac` before widening the range)

CUMULATIVE + IDEMPOTENT over v371.
"""

import os
import sys

W = os.environ.get("XNU_WORK") or sys.exit("patch_v372: set XNU_WORK")
P = os.path.join(W, "osfmk", "arm", "arm_init.c")
s = open(P, encoding="utf-8", errors="replace").read()

if "v372" in s:
    print("patch_v372: already applied -- skip")
    raise SystemExit(0)


def rep(text, old, new, label):
    c = text.count(old)
    if c != 1:
        sys.exit("patch_v372: %s anchor count=%d (want 1)" % (label, c))
    return text.replace(old, new, 1)


# --- 1. dirty row range next to the other console globals -------------------
A1 = "static unsigned int  g0245d_con_h;      /* g0245d v227: panel height */\n"
N1 = (A1 +
      "/* g0245d v372: rows painted since the last cache flush.  dlo > dhi\n"
      " * means nothing is dirty.\n"
      " */\n"
      "static unsigned int  g0245d_con_dlo = 0xFFFFFFFFu;\n"
      "static unsigned int  g0245d_con_dhi = 0;\n")
s = rep(s, A1, N1, "globals")

# --- 2. every pixel write records which text row it belongs to -------------
A2 = "\tv = on ? 0xFF : 0x00;\n"
N2 = ("\tv = on ? 0xFF : 0x00;\n"
      "\t{ unsigned int rr = y / G0245D_CON_CH;\n"
      "\t  if (rr < g0245d_con_dlo) {\n"
      "\t\t  g0245d_con_dlo = rr;\n"
      "\t  }\n"
      "\t  if (rr > g0245d_con_dhi) {\n"
      "\t\t  g0245d_con_dhi = rr;\n"
      "\t  } }\n")
s = rep(s, A2, N2, "px")

# --- 3. flush only the dirty rows, clean (not invalidate) ------------------
A3 = ('\tunsigned long p, end;\n'
      '\n'
      '\tif (!g0245d_con_ready) {\n'
      '\t\treturn;\n'
      '\t}\n'
      '\t/* g0245d v230: the status row sits below the scroll cursor, so flush\n'
      '\t * every text row instead of only the ones above the cursor. */\n'
      '\tend = (unsigned long)g0245d_con_base\n'
      '\t    + (unsigned long)g0245d_con_rows * G0245D_CON_CH * g0245d_con_stride;\n'
      '\tfor (p = (unsigned long)g0245d_con_base; p < end; p += 64) {\n'
      '\t\t__asm__ volatile ("dc civac, %0" :: "r"(p) : "memory");\n'
      '\t}\n')

N3 = ('\tunsigned long p, start, end, limit;\n'
      '\n'
      '\tif (!g0245d_con_ready) {\n'
      '\t\treturn;\n'
      '\t}\n'
      '\t/* g0245d v372: v230 cleaned+invalidated the whole text area on every\n'
      '\t * single line (~15k maintenance ops + a full DSB per line).  That is\n'
      '\t * the same class of op that hangs intermittently on msm8996 (v365\n'
      '\t * disabled `tlbi vmalle1` for exactly this reason), and it made the\n'
      '\t * freeze point wander with every added probe.  Flush only the rows\n'
      '\t * painted since the last sync, and clean instead of invalidate: the\n'
      '\t * display scans DRAM, so invalidation buys nothing and can discard\n'
      '\t * dirty lines.\n'
      '\t */\n'
      '\tif (g0245d_con_dlo > g0245d_con_dhi) {\n'
      '\t\treturn;\n'
      '\t}\n'
      '\tlimit = (unsigned long)g0245d_con_base\n'
      '\t    + (unsigned long)g0245d_con_rows * G0245D_CON_CH * g0245d_con_stride;\n'
      '\tstart = (unsigned long)g0245d_con_base\n'
      '\t    + (unsigned long)g0245d_con_dlo * G0245D_CON_CH * g0245d_con_stride;\n'
      '\tend = (unsigned long)g0245d_con_base\n'
      '\t    + ((unsigned long)g0245d_con_dhi + 1) * G0245D_CON_CH * g0245d_con_stride;\n'
      '\tif (end > limit) {\n'
      '\t\tend = limit;\n'
      '\t}\n'
      '\tfor (p = start; p < end; p += 64) {\n'
      '\t\t__asm__ volatile ("dc cvac, %0" :: "r"(p) : "memory");\n'
      '\t}\n'
      '\tg0245d_con_dlo = 0xFFFFFFFFu;\n'
      '\tg0245d_con_dhi = 0;\n')
s = rep(s, A3, N3, "sync")

# --- 4. boot-time marker so the kernel image self-identifies --------------
A4 = ('\tfor (r = 0; r < g0245d_con_rows; r++) {\n'
      '\t\tg0245d_con_fill_row(r);\n'
      '\t}\n')
N4 = (A4 +
      '\t{ extern void g0245d_status(const char *);\n'
      '\t  g0245d_status("v372 dirtyflush"); }\n')
s = rep(s, A4, N4, "marker")

open(P, "w", encoding="utf-8").write(s)
print("patch_v372: dirty-row, clean-only console flush installed")
print("patch_v372: done")
