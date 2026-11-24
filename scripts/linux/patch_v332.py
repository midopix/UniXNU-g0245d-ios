#!/usr/bin/env python3
"""g0245d v332 -- give the scratch page a legal wire tag, and watch the copyouts.

v331 confirmed the hypothesis: mach_vm_allocate_kernel(current_map(), ANYWHERE)
really does hand back 0x1000 (PID1's lowest hole after __PAGEZERO), and the
mapping is lazy.  But the wire attempt died on

    vm_resident.c:4618  Assertion failed: VM_KERN_MEMORY_NONE != (tag)

which comes from VM_OBJECT_WIRED_PAGE_UPDATE_END() in vm_object.h: wiring a
page requires a real memory tag (the tag feeds the ledger accounting).  Passing
VM_KERN_MEMORY_NONE for a wire is simply illegal; mach_vm_wire() takes the tag
from its caller for the same reason.

So: wire with VM_KERN_MEMORY_BSD (2).  If the pmap is healthy the page becomes
resident and the three copyout()s in load_init_program_at_path() stop faulting.

Probes:
  v332 alloc rc / v332 scratch    allocation result (expected 0 / 0x1000)
  v332 wire rc                   0 == page is resident
  v332 wired                     wire reported success
  v332 co path ok                path string copied out (no fault)
  v332 co argv ok                argv array copied out (no fault)

If the copyout probes never appear while wire rc is 0, the fault is not about
the page being absent, and the next suspect is copyio's exception recovery.
"""
import sys
import os

W = os.environ.get("XNU_WORK")
if not W:
    sys.exit("XNU_WORK not set")
F = os.path.join(W, "bsd/kern/kern_exec.c")
s = open(F).read()

if "v332 wire rc" in s:
    print("patch_v332: already applied")
    sys.exit(0)

# ---------------------------------------------------------------- 1. wire tag
OLD_TAG = "VM_PROT_READ | VM_PROT_WRITE, VM_KERN_MEMORY_NONE, TRUE);"
NEW_TAG = "VM_PROT_READ | VM_PROT_WRITE, VM_KERN_MEMORY_BSD, TRUE);"
assert s.count(OLD_TAG) == 1, s.count(OLD_TAG)
s = s.replace(OLD_TAG, NEW_TAG, 1)

# ------------------------------------------------------ 2. rename v331 probes
for name in ("v331 alloc rc", "v331 scratch", "v331 wire rc"):
    new = name.replace("v331", "v332")
    assert s.count('"%s"' % name) == 1, name
    s = s.replace('"%s"' % name, '"%s"' % new, 1)

# ------------------------------------------- 3. note success inside the block
OLD_WIRE = '\t\t\tg0245d_trace_u("v332 wire rc", (unsigned int)v331_wire);\n'
NEW_WIRE = ('\t\t\tg0245d_trace_u("v332 wire rc", (unsigned int)v331_wire);\n'
            '\t\t\tif (v331_wire == KERN_SUCCESS) {\n'
            '\t\t\t\tg0245d_trace("v332 wired");\n'
            '\t\t\t}\n')
assert s.count(OLD_WIRE) == 1
s = s.replace(OLD_WIRE, NEW_WIRE, 1)

# ------------------------------------- 4. probe after the path string copyout
OLD_PATH = ("\terror = copyout(path, argv0, path_length);\n"
            "\tif (error) {\n"
            "\t\treturn error;\n"
            "\t}\n")
NEW_PATH = ("\terror = copyout(path, argv0, path_length);\n"
            "\t{ extern void g0245d_trace(const char *);\n"
            "\t  if (error == 0) { g0245d_trace(\"v332 co path ok\"); } }\n"
            "\tif (error) {\n"
            "\t\treturn error;\n"
            "\t}\n")
assert s.count(OLD_PATH) == 1
s = s.replace(OLD_PATH, NEW_PATH, 1)

# ----------------------------------------- 5. probe after the argv copyout
OLD_ARGV = "\t\terror = copyout(argv64bit, scratch_addr, sizeof(argv64bit));\n"
NEW_ARGV = (OLD_ARGV +
            "\t\t{ extern void g0245d_trace(const char *);\n"
            "\t\t  if (error == 0) { g0245d_trace(\"v332 co argv ok\"); } }\n")
assert s.count(OLD_ARGV) == 1
s = s.replace(OLD_ARGV, NEW_ARGV, 1)

open(F, "w").write(s)
print("patch_v332: applied")
