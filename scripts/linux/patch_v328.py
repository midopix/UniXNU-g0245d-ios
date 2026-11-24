#!/usr/bin/env python3
"""g0245d v328: catch the crash on the exception path.

v327 hooked panic_trap_to_debugger and the hook never fired, yet the panel
still showed the debugger key map.  So the fault either bypasses that function
or enters DebuggerWithContext directly.  Two labels cover both:

  v328 ec <n>   - ESR exception class of the first synchronous exceptions
  v328 far <p>  - fault address of the same
  v328 dbg <m>  - the message handed to DebuggerWithContext (status row)

Only the first 12 synchronous exceptions are logged so a syscall storm cannot
wash the ring out.
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


patch(
    'osfmk/arm64/sleh.c',
    "sleh_synchronous(arm_context_t *context, uint32_t esr, vm_offset_t far)\n"
    "{\n"
    "\tesr_exception_class_t  class   = ESR_EC(esr);\n"
    "\tarm_saved_state_t    * state   = &context->ss;\n"
    "\tthread_t               thread  = current_thread();\n",
    "sleh_synchronous(arm_context_t *context, uint32_t esr, vm_offset_t far)\n"
    "{\n"
    "\tesr_exception_class_t  class   = ESR_EC(esr);\n"
    "\tarm_saved_state_t    * state   = &context->ss;\n"
    "\tthread_t               thread  = current_thread();\n"
    "\t/* g0245d v328: v327's panic hook never fired, so log the exception\n"
    "\t * class and fault address here instead.  Capped at 12 entries so a\n"
    "\t * syscall storm cannot wash the trace ring out. */\n"
    "\t{\n"
    "\t\tstatic int g0245d_sync_left = 12;\n"
    "\t\tif (g0245d_sync_left > 0) {\n"
    "\t\t\textern void g0245d_trace_u(const char *, unsigned int);\n"
    "\t\t\textern void g0245d_tracev(const char *, unsigned long long);\n"
    "\t\t\tg0245d_sync_left--;\n"
    "\t\t\tg0245d_trace_u(\"v328 ec\", (unsigned int)ESR_EC(esr));\n"
    "\t\t\tg0245d_tracev(\"v328 far\", (unsigned long long)far);\n"
    "\t\t}\n"
    "\t}\n",
    'sync-exception',
)

patch(
    'osfmk/kern/debug.c',
    "DebuggerWithContext(unsigned int reason, void *ctx, const char *message,\n"
    "    uint64_t debugger_options_mask, unsigned long debugger_caller)\n"
    "{\n"
    "\tspl_t previous_interrupts_state;\n",
    "DebuggerWithContext(unsigned int reason, void *ctx, const char *message,\n"
    "    uint64_t debugger_options_mask, unsigned long debugger_caller)\n"
    "{\n"
    "\t/* g0245d v328: whichever path enters the debugger, pin its message. */\n"
    "\t{ extern void g0245d_status(const char *);\n"
    "\t  g0245d_status(message != NULL ? message : \"v328 dbg no message\"); }\n"
    "\tspl_t previous_interrupts_state;\n",
    'debugger-entry',
)

print('patch_v328 done')
