#!/usr/bin/env python3
"""g0245d v327: surface the panic reason on screen.

Every panic funnels through panic_trap_to_debugger().  Before the debugger
redraws the panel (which buries the normal panic text under its key map), pin
the format string on both the status row and the scrolling trace ring, so the
next photo tells us the panic site directly instead of only the last probe.

Everything else stays at the v326 configuration.
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')
path = os.path.join(W, 'osfmk/kern/debug.c')

OLD = (
    'panic_trap_to_debugger(const char *panic_format_str, va_list *panic_args, unsigned int reason, void *ctx,\n'
    '    uint64_t panic_options_mask, void *panic_data_ptr, unsigned long panic_caller)\n'
    '{\n'
    '#pragma clang diagnostic pop\n'
)

NEW = (
    'panic_trap_to_debugger(const char *panic_format_str, va_list *panic_args, unsigned int reason, void *ctx,\n'
    '    uint64_t panic_options_mask, void *panic_data_ptr, unsigned long panic_caller)\n'
    '{\n'
    '#pragma clang diagnostic pop\n'
    '\n'
    '\t/* g0245d v327: the debugger redraws the panel with its key map and buries\n'
    '\t * the ordinary panic text.  Pin the format string first: the status row\n'
    '\t * survives the redraw, and the trace ring keeps a second copy.\n'
    '\t * Only the format string (no arguments) is shown, which is enough to name\n'
    '\t * the panic site.\n'
    '\t */\n'
    '\tif (panic_format_str != NULL) {\n'
    '\t\textern void g0245d_status(const char *);\n'
    '\t\textern void g0245d_trace(const char *);\n'
    '\t\tg0245d_status(panic_format_str);\n'
    '\t\tg0245d_trace("v327 panic");\n'
    '\t\tg0245d_trace(panic_format_str);\n'
    '\t}\n'
)

text = open(path, encoding='utf-8').read()
if 'v327 panic' in text:
    print('  panic hook: already applied')
else:
    if text.count(OLD) != 1:
        sys.exit(f'anchor count={text.count(OLD)}')
    open(path, 'w', encoding='utf-8').write(text.replace(OLD, NEW, 1))
    print('  panic hook: applied')
