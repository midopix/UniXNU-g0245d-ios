#!/usr/bin/env python3
"""v226: give XNU a real text console on the boot framebuffer.

Why: on this board XNU has no output channel at all.

  * pe_arm_get_soc_base_phys() returns 0 (the ADT has no arm-io node), so
    serial_init() bails out at pexpert/arm/pe_serial.c:774 *before* it
    registers a single driver -> no serial console, ever.
  * PE_init_printf() (which would install PE_kputc) is only reached after
    PE_create_console(), i.e. after the point where we currently stop.

So we draw text ourselves: iso_font glyphs written straight into the boot
framebuffer at the physical address firmware handed us. TTBR0 still maps
PA->PA for the whole arm_init() window (v223 keeps the identity mapping
alive after arm_vm_init), so the raw address stays writable.

Every existing colour-band probe also emits a text line, so a photo yields
readable messages instead of 47 colours to decode.
"""
import json
import re
import sys
from pathlib import Path

TREE = Path('$HOME/g0245d-clean/UniXNU-runtime/out/g0245d/ios-16.5-20F66/'
            'g0245d/tree/.cache/xnu-work')
ARM_INIT = TREE / 'osfmk/arm/arm_init.c'
VM_INIT = TREE / 'osfmk/arm64/arm_vm_init.c'
MANIFEST = Path('$G0245D_OUT/band-manifests/v225.json')

BEGIN = '/* ===== g0245d v226 console BEGIN ===== */'
END = '/* ===== g0245d v226 console END ===== */'

CONSOLE_C = r'''/* ===== g0245d v226 console BEGIN ===== */
/*
 * Text console on the boot framebuffer.
 *
 * serial_init() returns 0 on this board before registering any driver, and
 * PE_init_printf() is never reached, so up to now the kernel has had no way
 * to say anything. We therefore draw with iso_font directly into the frame
 * buffer that firmware handed over in args->Video.
 *
 * The console owns framebuffer rows 0..G0245D_CON_TOP; the colour-band
 * ladder keeps the rows above 1140. Text grows upward from row 0 (the row
 * that appears at the bottom of the panel), so the newest line is the
 * lowest one.
 */
extern unsigned char iso_font[256 * 16];
#include <stdarg.h>

#define G0245D_CON_SCALE   2
#define G0245D_CON_CW      (8 * G0245D_CON_SCALE)
#define G0245D_CON_CH      (16 * G0245D_CON_SCALE)
#define G0245D_CON_TOP     1140

static volatile unsigned char *g0245d_con_base;
static unsigned long g0245d_con_stride;
static unsigned int  g0245d_con_bpp;
static unsigned int  g0245d_con_cols;
static unsigned int  g0245d_con_rows;
static unsigned int  g0245d_con_col;
static unsigned int  g0245d_con_row;
static unsigned int  g0245d_con_ready;
static unsigned int  g0245d_con_seq;

static void
g0245d_con_px(unsigned int x, unsigned int y, unsigned int on)
{
	volatile unsigned char *p = g0245d_con_base
	    + (unsigned long)y * g0245d_con_stride
	    + (unsigned long)x * g0245d_con_bpp;
	unsigned char v = on ? 0xFF : 0x00;

	p[0] = v;
	p[1] = v;
	p[2] = v;
	if (g0245d_con_bpp > 3) {
		p[3] = 0xFF;
	}
}

static void
g0245d_con_fill_row(unsigned int row)
{
	unsigned int x, y;

	for (y = 0; y < G0245D_CON_CH; y++) {
		for (x = 0; x < g0245d_con_cols * G0245D_CON_CW; x++) {
			g0245d_con_px(x, row * G0245D_CON_CH + y, 0);
		}
	}
}

static void
g0245d_con_sync(void)
{
	unsigned long p, end;

	if (!g0245d_con_ready) {
		return;
	}
	end = (unsigned long)g0245d_con_base
	    + (unsigned long)(g0245d_con_row + 1) * G0245D_CON_CH * g0245d_con_stride;
	for (p = (unsigned long)g0245d_con_base; p < end; p += 64) {
		__asm__ volatile ("dc civac, %0" :: "r"(p) : "memory");
	}
	__asm__ volatile ("dsb sy" ::: "memory");
}

/* args->Video is filled in by the firmware; no ADT interpretation involved. */
static void
g0245d_con_init(boot_args *args)
{
	unsigned long base = args->Video.v_baseAddr;
	unsigned long stride = args->Video.v_rowBytes;
	unsigned long width = args->Video.v_width;
	unsigned long height = args->Video.v_height;
	unsigned int r;

	g0245d_con_ready = 0;
	if (base == 0 || stride == 0 || width == 0 || height == 0) {
		return;
	}
	if (width > 4096 || stride > 16384 || height > 4096) {
		return;
	}
	g0245d_con_base = (volatile unsigned char *)base;
	g0245d_con_stride = stride;
	g0245d_con_bpp = (stride >= width * 4) ? 4 : 3;
	g0245d_con_cols = (unsigned int)(width / G0245D_CON_CW);
	g0245d_con_rows = G0245D_CON_TOP / G0245D_CON_CH;
	g0245d_con_col = 0;
	g0245d_con_row = 0;
	if (g0245d_con_cols == 0 || g0245d_con_rows == 0) {
		return;
	}
	g0245d_con_ready = 1;
	for (r = 0; r < g0245d_con_rows; r++) {
		g0245d_con_fill_row(r);
	}
	g0245d_con_sync();
}

void
g0245d_con_putc(char c)
{
	const unsigned char *glyph;
	unsigned int gx, gy, sx, sy, x0, y0;

	if (!g0245d_con_ready) {
		return;
	}
	if (c == '\r') {
		g0245d_con_col = 0;
		return;
	}
	if (c == '\n' || g0245d_con_col >= g0245d_con_cols) {
		g0245d_con_col = 0;
		g0245d_con_row = (g0245d_con_row + 1) % g0245d_con_rows;
		g0245d_con_fill_row(g0245d_con_row);
		if (c == '\n') {
			return;
		}
	}
	glyph = iso_font + ((unsigned char)c) * 16;
	x0 = g0245d_con_col * G0245D_CON_CW;
	y0 = g0245d_con_row * G0245D_CON_CH;
	for (gy = 0; gy < 16; gy++) {
		for (gx = 0; gx < 8; gx++) {
			if ((glyph[gy] & (1u << gx)) == 0) {
				continue;
			}
			for (sy = 0; sy < G0245D_CON_SCALE; sy++) {
				for (sx = 0; sx < G0245D_CON_SCALE; sx++) {
					g0245d_con_px(x0 + gx * G0245D_CON_SCALE + sx,
					    y0 + gy * G0245D_CON_SCALE + sy, 1);
				}
			}
		}
	}
	g0245d_con_col++;
}

static void
g0245d_con_puts(const char *s)
{
	while (*s) {
		g0245d_con_putc(*s++);
	}
}

static void
g0245d_con_putu(unsigned long v, unsigned int base, unsigned int pad)
{
	char tmp[24];
	unsigned int n = 0;

	do {
		unsigned int d = (unsigned int)(v % base);
		tmp[n++] = (char)(d < 10 ? '0' + d : 'a' + d - 10);
		v /= base;
	} while (v && n < sizeof(tmp));
	while (n < pad) {
		tmp[n++] = '0';
	}
	while (n) {
		g0245d_con_putc(tmp[--n]);
	}
}

/* Tiny formatter: %s %c %d %u %x %p %% only. No locale, no locks. */
void
g0245d_con_printf(const char *fmt, ...)
{
	va_list ap;
	const char *s;

	if (!g0245d_con_ready) {
		return;
	}
	va_start(ap, fmt);
	while (*fmt) {
		if (*fmt != '%') {
			g0245d_con_putc(*fmt++);
			continue;
		}
		fmt++;
		switch (*fmt) {
		case 's':
			s = va_arg(ap, const char *);
			g0245d_con_puts(s ? s : "(null)");
			break;
		case 'c':
			g0245d_con_putc((char)va_arg(ap, int));
			break;
		case 'd':
			g0245d_con_putu((unsigned long)va_arg(ap, int), 10, 0);
			break;
		case 'u':
			g0245d_con_putu(va_arg(ap, unsigned int), 10, 0);
			break;
		case 'x':
			g0245d_con_putu(va_arg(ap, unsigned int), 16, 0);
			break;
		case 'p':
			g0245d_con_puts("0x");
			g0245d_con_putu((unsigned long)va_arg(ap, void *), 16, 0);
			break;
		case '%':
			g0245d_con_putc('%');
			break;
		case '\0':
			fmt--;
			break;
		default:
			g0245d_con_putc('%');
			g0245d_con_putc(*fmt);
			break;
		}
		fmt++;
	}
	va_end(ap);
	if (g0245d_con_seq++ % 8 == 7) {
		g0245d_con_sync();
	}
}

/*
 * A checkpoint: one text line, then the same colour band as before so the
 * old ladder keeps working as a fallback if the font path ever misbehaves.
 */
static void
g0245d_mark(boot_args *args, unsigned int row, unsigned char g, unsigned char r,
    unsigned char b, const char *label)
{
	g0245d_con_printf("%u row=%u %s\n", g0245d_con_seq, row, label);
	g0245d_fb_band(args, row, g, r, b);
	g0245d_con_sync();
}
/* ===== g0245d v226 console END ===== */
'''

# rows that live inside the console area are still useful as colour evidence
LABELS = {
    1440: 'arm_init body reached',
    1460: 'PE_init_platform returned',
    1480: 'pre-arm_vm_init tail done',
    1500: 'boot_progress_init returned',
    1520: 'timer regs configured',
    1540: 'cpu topology ready',
    1560: 'thread_bootstrap returned',
    1580: 'cpu_bootstrap returned',
    1600: 'timer_call_init returned',
    1640: 'processor_bootstrap returned',
    1660: 'entering timer/apple diag',
    1680: 'configure_timer_apple_regs done',
    1700: 'wfe block skipped (v217)',
    1720: 'after wfe skip',
    1740: 'before PE_init_platform tail',
    1760: 'arm_init entry',
    1400: 'arm_vm_init returned',
    1380: 'serial_init returned',
    1360: 'PE_init_printf returned',
    1140: 'PE_create_console returned',
    1120: 'serial boot-arg block done',
    1100: 'first kprintf returned',
    1080: 'startup_upto(KPRINTF) returned',
    1060: 'timer_call_init enter',
    1040: 'kernel_startup_bootstrap ret',
    1020: 'rtclock_early_init ret',
    1000: 'before rtclock_early_init',
    900: 'rtclock probe 900',
    920: 'rtclock probe 920',
    940: 'rtclock probe 940',
    960: 'rtclock probe 960',
    840: 'arm_vm_init probe 840',
    860: 'arm_vm_init probe 860',
    800: 'arm_vm_init probe 800',
    780: 'arm_vm_init probe 780',
    770: 'arm_vm_init probe 770',
    760: 'arm_vm_init probe 760',
    740: 'arm_vm_init probe 740',
    720: 'arm_vm_init probe 720',
    700: 'arm_vm_init probe 700',
    660: 'fb kva conversion ok',
    640: 'fb pa inside physmap',
    620: 'arm_vm_init entry',
}


def labels_from_manifest():
    try:
        m = json.loads(MANIFEST.read_text(encoding='utf-8'))
    except Exception:
        return
    for c in m.get('checkpoints', []):
        note = (c.get('note') or '').replace('/*', ' ').replace('*/', ' ').strip()
        if note and c['row'] not in LABELS:
            LABELS[c['row']] = note[:44]


BAND_RE = re.compile(
    r'g0245d_fb_band\(\s*args\s*,\s*(\d+)\s*,\s*(0x[0-9A-Fa-f]+|\d+)\s*,'
    r'\s*(0x[0-9A-Fa-f]+|\d+)\s*,\s*(0x[0-9A-Fa-f]+|\d+)\s*\)\s*;')


def rewrite_bands(text):
    n = 0

    def sub(m):
        nonlocal n
        row = int(m.group(1))
        label = LABELS.get(row, 'row %d' % row).replace('"', '')
        n += 1
        return ('g0245d_mark(args, %d, %s, %s, %s, "%s");'
                % (row, m.group(2), m.group(3), m.group(4), label))

    return BAND_RE.sub(sub, text), n


def patch_arm_init():
    s = ARM_INIT.read_text(encoding='utf-8')
    if BEGIN in s:
        head, rest = s.split(BEGIN, 1)
        s = head + rest.split(END, 1)[1]

    # drop the placeholder stub that never compiled
    s = s.replace('''static void
g0245d_con_clear_row(unsigned int row)
{
	unsigned long y0 = (unsigned long)row * G0245D_CON_CH_UNUSED;
	(void)y0;
}

''', '')

    # must come before g0245d_wfe_mark(), which now prints text too
    anchor = '/* g0245d v213: used only during the boot CPU\'s pre-arm_vm_init WFE setup.'
    if anchor not in s:
        anchor = 'arm_init(\n\tboot_args       *args)\n{'
    if anchor not in s:
        sys.exit('console insertion anchor not found')
    s = s.replace(anchor, CONSOLE_C + '\n' + anchor, 1)

    # console comes up right after the panel wipe, before anything is drawn
    wipe = '\tg0245d_fb_wipe(args);\n'
    if wipe not in s:
        sys.exit('fb_wipe anchor not found')
    if 'g0245d_con_init(args);' not in s:
        s = s.replace(wipe, wipe + '''
	/* g0245d v226: text console on the same framebuffer the bands use. */
	g0245d_con_init(args);
	g0245d_con_printf("G0245D XNU %s %s\\n", "v226", "text console");
	g0245d_con_printf("fb pa=%p stride=%u w=%u h=%u bpp=%u\\n",
	    (void *)args->Video.v_baseAddr,
	    (unsigned int)args->Video.v_rowBytes,
	    (unsigned int)args->Video.v_width,
	    (unsigned int)args->Video.v_height,
	    (unsigned int)args->Video.v_depth);
	g0245d_con_printf("cols=%u rows=%u physbase=%p\\n",
	    g0245d_con_cols, g0245d_con_rows, (void *)args->physBase);
''', 1)

    s, n = rewrite_bands(s)
    ARM_INIT.write_text(s, encoding='utf-8')
    return n


def patch_wrappers():
    """Any probe that goes through the wfe/pexpert wrappers also prints text."""
    s = ARM_INIT.read_text(encoding='utf-8')
    changed = 0

    old_wfe = '''	__asm__ volatile ("" :: "r"(value) : "memory");
	g0245d_fb_band(BootArgs, row, g, r, b);
}'''
    new_wfe = '''	__asm__ volatile ("" :: "r"(value) : "memory");
	g0245d_con_printf("%u wfe row=%u val=%p\\n",
	    g0245d_con_seq, row, (void *)(uintptr_t)value);
	g0245d_fb_band(BootArgs, row, g, r, b);
}'''
    if old_wfe in s:
        s = s.replace(old_wfe, new_wfe, 1)
        changed += 1

    old_here = '''	unsigned char   b)
{
	g0245d_fb_band(BootArgs, row, g, r, b);
}'''
    new_here = '''	unsigned char   b)
{
	g0245d_con_printf("%u pexpert row=%u\\n", g0245d_con_seq, row);
	g0245d_fb_band(BootArgs, row, g, r, b);
}'''
    if old_here in s:
        s = s.replace(old_here, new_here, 1)
        changed += 1

    ARM_INIT.write_text(s, encoding='utf-8')
    return changed


def main():
    labels_from_manifest()
    a = patch_arm_init()
    w = patch_wrappers()
    print('rewrote %d band calls in arm_init.c, %d wrappers instrumented' % (a, w))
    print('console: rows=%d cols=67 (scale 2, fb rows 0..1140)' % (1140 // 32))


if __name__ == '__main__':
    main()
