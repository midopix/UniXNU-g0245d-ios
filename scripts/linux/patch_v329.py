#!/usr/bin/env python3
"""g0245d v329: read out the actual errno and loop index.

v328 showed the panic format string ("Process 1 exec of %s failed, errno %d")
but %s/%d were never expanded, so we still do not know which path failed or
with what errno.  Two complementary changes:

  1. load_init_program: before the panic, emit `v329 pan i` and `v329 pan err`
     as their own trace lines, so neither value can be clipped by the status
     row width.
  2. panic hook: expand the format string with va_copy + vsnprintf and pin the
     result on the status row, plus print the panic caller address so the site
     can be resolved offline.
"""
import os
import sys

W = os.environ.get('XNU_WORK') or sys.exit('XNU_WORK not set')


def patch(rel, old, new, label):
    path = os.path.join(W, rel)
    text = open(path, encoding='utf-8').read()
    if new in text:
        print(f'  {label}: already applied')
        return
    if text.count(old) != 1:
        sys.exit(f'{label}: anchor count={text.count(old)} in {rel}')
    open(path, 'w', encoding='utf-8').write(text.replace(old, new, 1))
    print(f'  {label}: applied')


# 1) loop index and errno before the init_programs panic
patch(
    'bsd/kern/kern_exec.c',
    '\tpanic("Process 1 exec of %s failed, errno %d", ((i == 0) ? "<null>" : init_programs[i - 1]), error);\n',
    '\t/* g0245d v329: expose which attempt failed and with what errno; the\n'
    '\t * status row clips long formatted strings, so these get their own lines. */\n'
    '\t{ extern void g0245d_trace_u(const char *, unsigned int);\n'
    '\t  g0245d_trace_u("v329 pan i", (unsigned int)i);\n'
    '\t  g0245d_trace_u("v329 pan err", (unsigned int)error); }\n'
    '\tpanic("Process 1 exec of %s failed, errno %d", ((i == 0) ? "<null>" : init_programs[i - 1]), error);\n',
    'panic-args',
)

# 2) expand the panic message instead of showing the raw format string
patch(
    'osfmk/kern/debug.c',
    '\tif (panic_format_str != NULL) {\n'
    '\t\textern void g0245d_status(const char *);\n'
    '\t\textern void g0245d_trace(const char *);\n'
    '\t\tg0245d_status(panic_format_str);\n'
    '\t\tg0245d_trace("v327 panic");\n'
    '\t\tg0245d_trace(panic_format_str);\n'
    '\t}\n',
    '\tif (panic_format_str != NULL) {\n'
    '\t\textern void g0245d_status(const char *);\n'
    '\t\textern void g0245d_trace(const char *);\n'
    '\t\textern void g0245d_tracev(const char *, unsigned long long);\n'
    '\t\tchar v329_msg[160];\n'
    '\t\tva_list v329_copy;\n'
    '\t\tva_copy(v329_copy, *panic_args);\n'
    '\t\tvsnprintf(v329_msg, sizeof(v329_msg), panic_format_str, v329_copy);\n'
    '\t\tva_end(v329_copy);\n'
    '\t\tg0245d_status(v329_msg);\n'
    '\t\tg0245d_trace("v329 panic msg");\n'
    '\t\tg0245d_trace(v329_msg);\n'
    '\t\tg0245d_tracev("v329 pc", (unsigned long long)panic_caller);\n'
    '\t}\n',
    'panic-expand',
)

print('patch_v329 done')
