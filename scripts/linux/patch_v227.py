#!/usr/bin/env python3
"""v227: make the on-screen console trustworthy.

Three things, all in service of "never guess again":

1. Orientation.  The panel scans the frame buffer rotated 180 degrees, so the
   v226 text came out upside down.  Mirror both axes in g0245d_con_px().
2. Flushing.  v226 only flushed every 8th printf, so the last two or three
   lines a hang produced could stay in the cache and never reach the panel.
   Flush on every completed line.
3. Channel.  PE_init_kprintf() falls back to console_write_unbuffered() when
   serial_init() fails, which needs a video console we never get.  Install our
   own sink into PE_kputc so kprintf -- and therefore panic -- prints on screen.

It also stops calling check_for_panic_log(): its job is to salvage an iBoot
panic log out of the head of VRAM, our ADT has no 'pram' node, and the head of
VRAM is now this console's own canvas.
"""
import sys
from pathlib import Path

XNU = Path('$HOME/g0245d-clean/UniXNU-runtime/out/g0245d/ios-16.5-20F66/g0245d/tree/.cache/xnu-work')
ARM = XNU / 'osfmk/arm/arm_init.c'
PE = XNU / 'pexpert/arm/pe_init.c'


def sub1(text, old, new, what):
    if old not in text:
        sys.exit('anchor missing: %s' % what)
    if new.strip().split('\n')[0] in text and old == new:
        return text
    return text.replace(old, new, 1)


s = ARM.read_text(encoding='utf-8')
if 'g0245d v227' in s:
    sys.exit('arm_init.c already patched')

# ---------------------------------------------------------------- 1. globals
s = sub1(
    s,
    "static unsigned int  g0245d_con_ready;\n"
    "static unsigned int  g0245d_con_seq;\n",
    "static unsigned int  g0245d_con_ready;\n"
    "static unsigned int  g0245d_con_seq;\n"
    "static unsigned int  g0245d_con_w;      /* g0245d v227: panel width  */\n"
    "static unsigned int  g0245d_con_h;      /* g0245d v227: panel height */\n",
    'con statics')

# ------------------------------------------------------------- 2. pixel flip
s = sub1(
    s,
    "	volatile unsigned char *p = g0245d_con_base\n"
    "	    + (unsigned long)y * g0245d_con_stride\n"
    "	    + (unsigned long)x * g0245d_con_bpp;\n",
    "	/* g0245d v227: the panel scans the frame buffer rotated by 180\n"
    "	 * degrees (fb row 0 lands at the bottom of the panel and x grows to\n"
    "	 * the left), so every pixel must be written mirrored on both axes or\n"
    "	 * the text comes out upside down.\n"
    "	 */\n"
    "	volatile unsigned char *p = g0245d_con_base\n"
    "	    + (unsigned long)(g0245d_con_h - 1 - y) * g0245d_con_stride\n"
    "	    + (unsigned long)(g0245d_con_w - 1 - x) * g0245d_con_bpp;\n",
    'con_px')

# --------------------------------------------------------- 3. remember panel
s = sub1(
    s,
    "	g0245d_con_stride = stride;\n",
    "	g0245d_con_stride = stride;\n"
    "	g0245d_con_w = (unsigned int)width;\n"
    "	g0245d_con_h = (unsigned int)height;\n",
    'con_init dims')

# ------------------------------------------------------- 4. flush every line
s = sub1(
    s,
    "		g0245d_con_fill_row(g0245d_con_row);\n"
    "		if (c == '\\n') {\n"
    "			return;\n"
    "		}\n",
    "		g0245d_con_fill_row(g0245d_con_row);\n"
    "		if (c == '\\n') {\n"
    "			/* g0245d v227: flush every completed line.  In v226 only\n"
    "			 * every 8th printf was flushed, so a hang could leave up\n"
    "			 * to three finished lines sitting in the cache and the\n"
    "			 * last visible checkpoint was up to three steps stale.\n"
    "			 */\n"
    "			g0245d_con_sync();\n"
    "			return;\n"
    "		}\n",
    'putc newline sync')

# ----------------------------------------------------- 5. kprintf -> fbcon
s = sub1(
    s,
    "	/* g0245d v220: mark 1360 - printf/console initialised. */\n"
    "	g0245d_mark(args, 1360, 0xE0, 0xFF, 0xE0, \"PE_init_printf returned\");\n",
    "	/* g0245d v220: mark 1360 - printf/console initialised. */\n"
    "	g0245d_mark(args, 1360, 0xE0, 0xFF, 0xE0, \"PE_init_printf returned\");\n"
    "\n"
    "	/* g0245d v227: PE_init_kprintf() falls back to\n"
    "	 * console_write_unbuffered() because serial_init() returns 0 here,\n"
    "	 * and that needs a video console we never manage to build.  Point\n"
    "	 * the kernel's kprintf sink at this console instead, so from here on\n"
    "	 * every kprintf()/panic() lands on the panel as text.\n"
    "	 */\n"
    "	PE_kputc = g0245d_con_putc;\n"
    "	g0245d_mark(args, 1340, 0x20, 0x20, 0xFF, \"kprintf routed to fb console\");\n",
    'kputc install')

ARM.write_text(s, encoding='utf-8')

# ------------------------------------------------------------------ pe_init.c
p = PE.read_text(encoding='utf-8')
if 'g0245d v227' in p:
    sys.exit('pe_init.c already patched')

old_body = """	g0245d_band_here(1200, 0xFF, 0xFF, 0x00);	/* g0245d v225: entered PE_create_console */
	check_for_panic_log();
	g0245d_band_here(1220, 0xFF, 0x00, 0xFF);	/* g0245d v225: check_for_panic_log returned */

	if (PE_state.video.v_display) {
		PE_initialize_console(&PE_state.video, kPEGraphicsMode);
	} else {
		PE_initialize_console(&PE_state.video, kPETextMode);
	}
	g0245d_band_here(1240, 0x00, 0xFF, 0xFF);	/* g0245d v225: PE_initialize_console returned */
	g0245d_band_here(1260, 0xFF, 0x80, 0x00);	/* g0245d v225: PE_create_console leaving */
"""

new_body = """	extern void g0245d_con_putc(char c);
	extern void g0245d_con_printf(const char *fmt, ...);

	/* g0245d v227: take over kprintf before anything else can print, so a
	 * panic inside this function still shows up as text on the panel.
	 */
	PE_kputc = g0245d_con_putc;

	g0245d_band_here(1200, 0xFF, 0xFF, 0x00);	/* g0245d v225: entered PE_create_console */
	g0245d_con_printf("v227 video: disp=%u base=%p stride=%u w=%u h=%u depth=%u\\n",
	    (unsigned int)PE_state.video.v_display,
	    (void *)(uintptr_t)PE_state.video.v_baseAddr,
	    (unsigned int)PE_state.video.v_rowBytes,
	    (unsigned int)PE_state.video.v_width,
	    (unsigned int)PE_state.video.v_height,
	    (unsigned int)PE_state.video.v_depth);

	/* g0245d v227: check_for_panic_log() is deliberately not called.  It
	 * wants the iBoot 'pram' node to salvage a panic log from the head of
	 * VRAM; our ADT has no such node, and the head of VRAM is this
	 * console's own canvas, so at best it returns and at worst it walks a
	 * mapping we never made.
	 */
	g0245d_band_here(1206, 0xFF, 0x00, 0x7F);	/* g0245d v227: panic-log probe skipped */

	if (PE_state.video.v_display) {
		g0245d_band_here(1212, 0x00, 0xFF, 0x7F);	/* g0245d v227: graphics mode */
		PE_initialize_console(&PE_state.video, kPEGraphicsMode);
	} else {
		g0245d_band_here(1218, 0x7F, 0xFF, 0x00);	/* g0245d v227: text mode */
		PE_initialize_console(&PE_state.video, kPETextMode);
	}
	g0245d_band_here(1240, 0x00, 0xFF, 0xFF);	/* g0245d v225: PE_initialize_console returned */
	g0245d_band_here(1260, 0xFF, 0x80, 0x00);	/* g0245d v225: PE_create_console leaving */
"""

p = sub1(p, old_body, new_body, 'PE_create_console body')
PE.write_text(p, encoding='utf-8')
print('patched %s and %s' % (ARM, PE))
