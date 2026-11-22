#!/usr/bin/env python3
"""v231: rotate the console 300 pixels inside the row, and add a column ruler.

The v230 photo says the text is not where we put it.  Each trace line shows
its first ~19 characters flush against the panel's right edge and its tail
flush against the left edge, with a dead band in between, and the missing
characters are exactly the ones that fell off the right edge.  That is a
scan-out window rotated inside the row: a run written at console column 0
appears 300 px to the right and wraps at the right edge back to the left.

So g0245d_con_px() now mirrors (as the 180-degree panel requires) and then
rotates by G0245D_CON_XOFF = 300, measured from that photo.

Because 300 is a measured guess, this build also paints a permanent ruler on
console row rows-2: 'A'..'Z', 'a'..'z', '0'..'9', then '!@#$%^&'.  Every
character in that range is unique, so one photo gives the exact screen column
of console column 0 and the value can be corrected in v232 if needed.  Rows
rows-2 (ruler) and rows-1 (status) both live outside the scroll ring.
"""
import glob
import os
import sys

CANDIDATES = [
    os.path.expanduser('~/g0245d-clean/UniXNU-runtime/out/g0245d/'
                       'ios-16.5-20F66/g0245d/tree/.cache/xnu-work'),
]
CANDIDATES += glob.glob('/home/*/g0245d-clean/UniXNU-runtime/out/g0245d/'
                        '*/g0245d/tree/.cache/xnu-work')
XNU = next((c for c in CANDIDATES if os.path.isdir(os.path.join(c, 'osfmk/arm'))), None)
if XNU is None:
    sys.exit('cannot find xnu-work')

ARM = os.path.join(XNU, 'osfmk/arm/arm_init.c')
src = open(ARM).read()


def sub(text, old, new, what):
    if text.count(old) != 1:
        sys.exit('anchor %s: %d hits' % (what, text.count(old)))
    print('patch', what)
    return text.replace(old, new)


src = sub(src,
          '#define G0245D_CON_TOP     1140\n',
          '#define G0245D_CON_TOP     1140\n'
          '\n'
          '/* g0245d v231: the scan-out window is rotated by this many pixels\n'
          ' * inside each framebuffer row.  The v230 photo showed a run written\n'
          ' * at console column 0 landing at screen x 780 of 1080, wrapping at\n'
          ' * the right edge back to the left edge, so the rotation is\n'
          ' * 1080 - 780 = 300 px.  Every mirrored x has to be moved by it.\n'
          ' */\n'
          '#define G0245D_CON_XOFF    300\n',
          'xoff define')

src = sub(src,
          'static void\n'
          'g0245d_con_px(unsigned int x, unsigned int y, unsigned int on)\n'
          '{\n',
          'static void\n'
          'g0245d_con_px(unsigned int x, unsigned int y, unsigned int on)\n'
          '{\n'
          '\tint fx;\n',
          'px decl')

src = sub(src,
          '\tvolatile unsigned char *p = g0245d_con_base\n'
          '\t    + (unsigned long)(g0245d_con_h - 1 - y) * g0245d_con_stride\n'
          '\t    + (unsigned long)(g0245d_con_w - 1 - x) * g0245d_con_bpp;\n',
          '\t/* g0245d v231: mirror for the 180-degree scan, then rotate by\n'
          '\t * G0245D_CON_XOFF so that console column 0 really lands on the\n'
          '\t * panel\'s left edge and the line stops wrapping mid-word.\n'
          '\t */\n'
          '\tfx = (int)(g0245d_con_w - 1 - x) - G0245D_CON_XOFF;\n'
          '\tif (fx < 0) {\n'
          '\t\tfx += (int)g0245d_con_w;\n'
          '\t}\n'
          '\tvolatile unsigned char *p = g0245d_con_base\n'
          '\t    + (unsigned long)(g0245d_con_h - 1 - y) * g0245d_con_stride\n'
          '\t    + (unsigned long)fx * g0245d_con_bpp;\n',
          'px body')

src = sub(src,
          '\tg0245d_con_nscroll = (g0245d_con_rows > 1) ?\n'
          '\t    g0245d_con_rows - 1 : g0245d_con_rows;\n',
          '\t/* g0245d v231: row rows-2 is the column ruler and row rows-1 the\n'
          '\t * status line; neither is in the ring, so both stay put. */\n'
          '\tg0245d_con_nscroll = (g0245d_con_rows > 2) ?\n'
          '\t    g0245d_con_rows - 2 : g0245d_con_rows;\n',
          'nscroll')

RULER = '''
/* g0245d v231: one permanent row of unique characters -- 'A'..'Z',
 * 'a'..'z', '0'..'9', then "!@#$%^&".  Any character read off a photo then
 * names its own console column, so the x-rotation above can be calibrated
 * from a single picture instead of guessed twice.
 */
static void
g0245d_con_ruler(void)
{
	static const char ruler[] =
	    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&";
	unsigned int    row;
	unsigned int    i;

	if (!g0245d_con_ready || g0245d_con_rows < 3) {
		return;
	}
	row = g0245d_con_rows - 2;
	g0245d_con_fill_row(row);
	for (i = 0; i < g0245d_con_cols && ruler[i] != '\\0'; i++) {
		g0245d_con_row = row;
		g0245d_con_col = i;
		g0245d_con_putc(ruler[i]);
	}
	g0245d_con_row = 0;
	g0245d_con_col = 0;
	g0245d_con_sync();
}

'''

src = sub(src,
          'static void\ng0245d_con_putu(unsigned long v, unsigned int base, unsigned int pad)',
          RULER + 'static void\ng0245d_con_putu(unsigned long v, unsigned int base, unsigned int pad)',
          'ruler fn')

src = sub(src,
          '\tg0245d_con_printf("G0245D XNU %s %s\\n", "v230", "trace+status");\n',
          '\tg0245d_con_printf("G0245D XNU %s %s\\n", "v231", "xalign+ruler");\n',
          'banner')

src = sub(src,
          '\tg0245d_con_printf("cols=%u rows=%u physbase=%p\\n",\n'
          '\t    g0245d_con_cols, g0245d_con_rows, (void *)args->physBase);\n',
          '\tg0245d_con_printf("cols=%u rows=%u physbase=%p xoff=%u\\n",\n'
          '\t    g0245d_con_cols, g0245d_con_rows, (void *)args->physBase,\n'
          '\t    (unsigned int)G0245D_CON_XOFF);\n'
          '\tg0245d_con_ruler();\n',
          'ruler call')

open(ARM, 'w').write(src)
print('wrote', ARM)
