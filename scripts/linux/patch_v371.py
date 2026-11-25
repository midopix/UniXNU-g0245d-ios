#!/usr/bin/env python3
"""patch_v371 -- bisect the pmap_switch entry window (v370 photo evidence).

Evidence (v370 screen, 2026-11-25 14:53:50):
  hb307 8692/8648 v356 pre      <- trace_seq 8692, last label "v356 pre"
  ring tail: 8691 v356 post 0xfffffff007a5b1f8
  status    : >v363 post

Reading (source order, osfmk/arm/pmap/pmap.c):
  pmap_switch():
      PMAP_TRACE(START)
      tracev("v356 pre")
      pmap_switch_internal(pmap)        <-- called directly on this build
      status("v370 a")
      tracev("v356 post")
      status("v363 post")
      PMAP_TRACE(END)

  so seq 8691 "post" + status "v363 post" prove one whole switch returned, and
  seq 8692 "pre" is the NEXT switch getting as far as its entry trace and then
  stopping: no "v357 s1", no new hb.  Window =
      tracev("v356 pre") returns  ->  pmap_switch_internal() entry
      -> pmap_get_cpu_data() -> validate_pmap_mutable() -> tracev("v357 s1")

  Note: pmap_switch is also called from arm64/pcb.c
  (machine_switch_pmap_and_extended_context, i.e. real thread switches), and a
  pcb.c switch has no preceding "v356 spmap".  v370 therefore reached thread
  context switching, later than any previous build.

This patch bisects that window with status-only sentinels (status does not
consume a trace seq and does not scroll the ring, so it survives ring overwrite
and reports the exact stop point without perturbing the ring):

  v371 lr / v371 ttep / v371 asid : trace lines, identify the caller of
                                    pmap_switch and the incoming pmap
  v371 p1 : inside pmap_switch, right after "v356 pre"
  v371 i0 : first statement of pmap_switch_internal (entered the function)
  v371 i1 : pmap_get_cpu_data() returned
  v371 i2 : validate_pmap_mutable() returned, about to trace "v357 s1"

Reading rules for the next photo (last status):
  still "v363 post" -> hung before/inside the "v371 p1" write itself
  "v371 p1"         -> hung on the call/branch into pmap_switch_internal
  "v371 i0"         -> hung inside pmap_get_cpu_data()
  "v371 i1"         -> hung in validate_pmap_mutable()
  "v371 i2"         -> hung inside the "v357 s1" console write (scrolling path)
  "v357 s1" in ring -> window passed, read the new ring tail

Additive only, no behaviour change. CUMULATIVE + IDEMPOTENT over v370.
"""

import os
import sys

W = os.environ.get("XNU_WORK") or sys.exit("patch_v371: set XNU_WORK")
P = os.path.join(W, "osfmk", "arm", "pmap", "pmap.c")
s = open(P, encoding="utf-8", errors="replace").read()

if "v371 i0" in s:
    print("patch_v371: already applied -- skip")
    raise SystemExit(0)

ST = '\t{ extern void g0245d_status(const char *);\n\t  g0245d_status("%s"); }\n'
TR = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("%s", %s); }\n')


def rep(text, old, new, label):
    c = text.count(old)
    if c != 1:
        sys.exit("patch_v371: %s anchor count=%d (want 1)" % (label, c))
    return text.replace(old, new, 1)


# --- 1. caller + incoming pmap, then pre, then p1 ---------------------------
A1 = ('\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v356 pre", (unsigned long long)(uintptr_t)pmap); }\n')

NEW1 = (TR % ("v371 lr", "(unsigned long long)(uintptr_t)__builtin_return_address(0)")
        + TR % ("v371 ttep", "(unsigned long long)(uintptr_t)pmap->ttep")
        + TR % ("v371 asid", "(unsigned long long)pmap->hw_asid")
        + A1
        + ST % "v371 p1")
s = rep(s, A1, NEW1, "pre")

# --- 2. i0 / i1: entered pmap_switch_internal, then cpu data is valid -------
A2 = ("pmap_switch_internal(\n"
      "\tpmap_t pmap)\n"
      "{\n"
      "\tpmap_cpu_data_t *cpu_data_ptr = pmap_get_cpu_data();\n")

NEW2 = ("pmap_switch_internal(\n"
        "\tpmap_t pmap)\n"
        "{\n"
        "\tpmap_cpu_data_t *cpu_data_ptr;\n"
        + ST % "v371 i0"
        + "\tcpu_data_ptr = pmap_get_cpu_data();\n"
        + ST % "v371 i1")
s = rep(s, A2, NEW2, "internal top")

# --- 3. i2: about to emit "v357 s1" ---------------------------------------
A3 = ('\tvalidate_pmap_mutable(pmap);\n'
      '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
      '\t  g0245d_tracev("v357 s1", (unsigned long long)(uintptr_t)pmap); }\n')

NEW3 = ('\tvalidate_pmap_mutable(pmap);\n'
        + ST % "v371 i2"
        + '\t{ extern void g0245d_tracev(const char *, unsigned long long);\n'
          '\t  g0245d_tracev("v357 s1", (unsigned long long)(uintptr_t)pmap); }\n')
s = rep(s, A3, NEW3, "s1")

open(P, "w", encoding="utf-8").write(s)
print("patch_v371: lr/ttep/asid traces + p1/i0/i1/i2 sentinels added")
print("patch_v371: done")
