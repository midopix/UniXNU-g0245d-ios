#!/usr/bin/env python3
import sys
p='/home/myth/WorkBuddy/2026-11-20-09-43-50/repos/UniXNU-g0245d-ios/board.toml'
text=open(p).read()
mode=sys.argv[1] if len(sys.argv)>1 else 'panic'
# Remove any prior probe config block first
import re
text=re.sub(r'\n# \[G0245D-PROBE[^\n]*\n(?:[^\n]*\n)*?(?=\n|\Z)', '\n', text)
for key in ('panic_screen','entry_probe_reset_delay','entry_probe_reset_after','entry_probe_reset_in','entry_probe_reset_occurrence','entry_probe_reset_before'):
    text=re.sub(r'(?m)^%s\s*=.*\n' % key, '', text)

if mode=='panic':
    block='''
# [G0245D-PROBE v457prb] Official Stage-5 panic screen: draw panic() format
# string on the framebuffer when the kernel faults before its own console.
# No reset probe (the panic screen 0xa2f bytes needs the full cave padding).
panic_screen = true
'''
elif mode=='reset4':
    block='''
# [G0245D-PROBE v458prb] Official Stage-5 stage-4 reset probe: timed PSCI
# reset after the 1st call to _arm_vm_init in _arm_init. A reboot after the
# delay means the CPU got past arm_vm_init; no reboot means it is stuck before.
entry_probe_reset_delay = 8
entry_probe_reset_after = "_arm_vm_init"
entry_probe_reset_in = "_arm_init"
entry_probe_reset_occurrence = 1
'''
elif mode=='reset4before':
    block='''
# [G0245D-PROBE] stage-4 reset BEFORE the 1st _arm_vm_init call.
entry_probe_reset_delay = 8
entry_probe_reset_after = "_arm_vm_init"
entry_probe_reset_in = "_arm_init"
entry_probe_reset_occurrence = 1
entry_probe_reset_before = true
'''
else:
    raise SystemExit('unknown mode '+mode)

# Insert right after the [payload] header line's size_mib entry (inside [payload])
marker='size_mib = 24\n'
assert marker in text, 'size_mib marker missing'
text=text.replace(marker, marker+block, 1)
open(p,'w').write(text)
print('wrote mode='+mode)
# show result
for line in text.splitlines():
    if 'PROBE' in line or 'panic_screen' in line or 'entry_probe' in line:
        print('  '+line)
