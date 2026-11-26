#!/usr/bin/env python3
"""g0245d v386: C1a verdict pinned-row probe.

Why: the v385 probes live in NativeUfs8996::start() and print into the
scrolling trace ring.  IOKit matching runs from pexpert (pe_init.c
StartIOKitMatching), so by the time the load_init_program panic
("v381 lret=2 @kern_exec.c:1336", the v382 steady state) freezes the screen
the ring has wrapped through ~9000 lines and every v385 line is scrolled
away.  A photo can therefore never answer C1a with the v385 image.

v386 adds ONE unconditional probe in bsdinit_task(), immediately before
load_init_program(): map 0x624000 with ml_io_map, read CAP/VER/HCPID
read-only (HCE is never written), and print one pinned row via
g0245d_probe() (rows-3, the row that survived every photo so far):

    v386 c=<cap8> v=<ver8> p=<hcpid8> m<n> s<n>

- c/v/p: direct MMIO reads, independent of IOKit matching.
  VER non-zero and not 0xffffffff => LK left the UFS clocks on (C1a pass).
  0 / all-ones => clocks gated, go to C1b (GCC clock enable).
- m: NativeUfs8996::probe() matched the root nub (ufs8996_matched, 0/1).
- s: how far start() got (ufs8996_step 0..5; 0 = personality never started).

Nothing between this probe and the panic calls g0245d_probe again, so the
line is the last writer of rows-3 and survives on screen.

Idempotent via the "g0245d v386" marker in bsd/kern/bsd_init.c.
"""
import os
import sys
from pathlib import Path

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set (path to the .cache/xnu-work tree)")
BSD = Path(W) / "bsd" / "kern" / "bsd_init.c"
if not BSD.is_file():
    sys.exit("required file not found: %s" % BSD)

src = BSD.read_text(encoding="utf-8")
if "g0245d v386" in src:
    print("patch_v386: already applied -- skip")
    sys.exit(0)

anchor = (
    '\t{ extern void g0245d_trace(const char *); '
    'g0245d_trace("v320 lip call"); }\n'
)
count = src.count(anchor)
if count != 1:
    sys.exit("patch_v386: v320 lip call anchor found %d times" % count)

probe = r'''	/* g0245d v386: C1a verdict on the pinned probe row (rows-3).
	 * ml_io_map + read-only UFSHCI reads, independent of IOKit matching.
	 * CAP=0x00, VER=0x08, HCPID=0x10 (CAF msm-3.18 ufshci.h).  HCE is
	 * never written.  m/s report the v385 driver: probe() matched the
	 * root nub (ufs8996_matched) and how far start() got (ufs8996_step,
	 * 0 = personality never started).  Nothing between here and the
	 * load_init_program panic calls g0245d_probe again, so this line is
	 * the last writer of rows-3 and survives on screen. */
	{
		extern volatile unsigned int ufs8996_matched;
		extern volatile unsigned int ufs8996_step;
		extern vm_offset_t ml_io_map(vm_offset_t, vm_size_t);
		vm_offset_t v386_uio = ml_io_map(0x624000, 0x1000);
		if (v386_uio != 0) {
			const volatile unsigned int *v386_r =
			    (const volatile unsigned int *)v386_uio;
			unsigned int v386_cap = v386_r[0x00 >> 2];
			unsigned int v386_ver = v386_r[0x08 >> 2];
			unsigned int v386_pid = v386_r[0x10 >> 2];
			static char v386_buf[48];
			const char v386_hex[] = "0123456789abcdef";
			const char *v386_pfx = "v386 c=";
			unsigned int v386_i = 0;
			unsigned int v386_j;
			while (*v386_pfx != '\0') {
				v386_buf[v386_i++] = *v386_pfx++;
			}
			for (v386_j = 0; v386_j < 8; v386_j++) {
				v386_buf[v386_i++] =
				    v386_hex[(v386_cap >> (28 - 4 * v386_j)) & 0xf];
			}
			v386_buf[v386_i++] = ' ';
			v386_buf[v386_i++] = 'v';
			v386_buf[v386_i++] = '=';
			for (v386_j = 0; v386_j < 8; v386_j++) {
				v386_buf[v386_i++] =
				    v386_hex[(v386_ver >> (28 - 4 * v386_j)) & 0xf];
			}
			v386_buf[v386_i++] = ' ';
			v386_buf[v386_i++] = 'p';
			v386_buf[v386_i++] = '=';
			for (v386_j = 0; v386_j < 8; v386_j++) {
				v386_buf[v386_i++] =
				    v386_hex[(v386_pid >> (28 - 4 * v386_j)) & 0xf];
			}
			v386_buf[v386_i++] = ' ';
			v386_buf[v386_i++] = 'm';
			v386_buf[v386_i++] =
			    (ufs8996_matched != 0) ? '1' : '0';
			v386_buf[v386_i++] = ' ';
			v386_buf[v386_i++] = 's';
			v386_buf[v386_i++] = (ufs8996_step < 10)
			    ? (char)('0' + ufs8996_step) : '?';
			v386_buf[v386_i] = '\0';
			{ extern void g0245d_probe(const char *);
			  g0245d_probe(v386_buf); }
			{ extern void g0245d_trace(const char *);
			  extern void g0245d_trace_u(const char *, unsigned int);
			  g0245d_trace("v386 ufs read ok");
			  g0245d_trace_u("v386 ver", v386_ver); }
		} else {
			{ extern void g0245d_probe(const char *);
			  g0245d_probe("v386 ml_io_map fail"); }
		}
	}
'''

src = src.replace(anchor, probe + anchor, 1)
BSD.write_text(src, encoding="utf-8")
print("patch_v386: bsdinit_task pinned-row UFS probe inserted before load_init_program")
