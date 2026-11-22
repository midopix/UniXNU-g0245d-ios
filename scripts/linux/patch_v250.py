#!/usr/bin/env python3
"""g0245d v250 -- open up vfsinit() and the DEVELOPMENT probes after it.

v249's photo is the first one with the 47 bsd_init stage names on the panel:

    8086 v249 kperf early skipped
    8087 v248 kperf done
    8088 v248 bsd init enter
    8089 v248 bsd body enter
    8090 bsd calling kauth_init
    8091 bsd calling process_name
    8092 bsd calling get_bsdthread_info
    8093 bsd calling kauth_cred_create
    8094 bsd calling chgproccnt
    8095 bsd calling kmem_suballoc
    8096 bsd calling bsd_bufferinit
    8097 bsd calling IOKitInitializeTime
    8098 bsd calling vfsinit
    (nothing more)

Note 8095: kmem_suballoc passed, so kmem_alloc itself is fine -- the
cpu_stack_alloc hang was specific to its flags/window, not a general failure.

bsd_init.c calls vfsinit() right after printing "calling vfsinit"; the next
stage name is "proc_uuid_policy_init" 25 lines later, with a DEVELOPMENT block
of native_apfs/graphics/iogpu/... probes in between, none of which is traced.
v250 brackets vfsinit(), each of its internal steps, each registered
filesystem's vfs_init, and each of those probes.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

BSD = os.path.join(WORK, "bsd/kern/bsd_init.c")
VFS = os.path.join(WORK, "bsd/vfs/vfs_init.c")

MARK = "g0245d v250"


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def write(p, s):
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)


def sub(src, old, new, what):
    n = src.count(old)
    if n != 1:
        sys.exit("%s: anchor found %d times" % (what, n))
    return src.replace(old, new)


# ------------------------------------------------------------- bsd_init.c
s = read(BSD)
if MARK not in s:
    s = sub(
        s,
        """	bsd_init_kprintf("calling vfsinit\\n");
	vfsinit();""",
        """	bsd_init_kprintf("calling vfsinit\\n");
	g0245d_trace("v250 vfs enter");
	vfsinit();
	g0245d_trace("v250 vfs done");""",
        "bsd_init: vfsinit bracket",
    )
    s = sub(
        s,
        """	native_apfs_load_probe();""",
        """	g0245d_trace("v250 apfs probe enter");
	native_apfs_load_probe();
	g0245d_trace("v250 apfs probe done");""",
        "bsd_init: apfs probe",
    )
    s = sub(
        s,
        """	native_mobile_graphics_load_probe();""",
        """	g0245d_trace("v250 graphics probe enter");
	native_mobile_graphics_load_probe();
	g0245d_trace("v250 graphics probe done");""",
        "bsd_init: graphics probe",
    )
    s = sub(
        s,
        """	native_iogpu_load_probe();""",
        """	g0245d_trace("v250 iogpu probe enter");
	native_iogpu_load_probe();
	g0245d_trace("v250 iogpu probe done");""",
        "bsd_init: iogpu probe",
    )
    write(BSD, s)
    print("bsd_init: v250 changes applied")
else:
    print("bsd_init: already patched")

# -------------------------------------------------------------- vfs_init.c
s = read(VFS)
if MARK not in s:
    s = sub(
        s,
        "#include <sys/param.h>",
        """#include <sys/param.h>

/* g0245d v250: framebuffer console traces, from osfmk/arm/arm_init.c. */
extern void g0245d_trace(const char *label);
extern void g0245d_trace_seg(const char *label, const char *text);""",
        "vfs_init: externs",
    )

    s = sub(
        s,
        """	vntblinit();""",
        """	g0245d_trace("v250 vntblinit enter");
	vntblinit();
	g0245d_trace("v250 vntblinit done");""",
        "vfs_init: vntblinit",
    )
    s = sub(
        s,
        """	vfs_event_init();""",
        """	g0245d_trace("v250 vfs event enter");
	vfs_event_init();
	g0245d_trace("v250 vfs event done");""",
        "vfs_init: vfs_event_init",
    )
    s = sub(
        s,
        """	nchinit();""",
        """	g0245d_trace("v250 nchinit enter");
	nchinit();
	g0245d_trace("v250 nchinit done");""",
        "vfs_init: nchinit",
    )
    s = sub(
        s,
        """	vfs_op_init();
	vfs_opv_init();   /* finish the job */""",
        """	g0245d_trace("v250 vfs op enter");
	vfs_op_init();
	vfs_opv_init();   /* finish the job */
	g0245d_trace("v250 vfs op done");""",
        "vfs_init: op vectors",
    )
    s = sub(
        s,
        """		(*vfsp->vfc_vfsops->vfs_init)(&vfsc);""",
        """		g0245d_trace_seg("v250 fs", vfsp->vfc_name);
		(*vfsp->vfc_vfsops->vfs_init)(&vfsc);
		g0245d_trace("v250 fs done");""",
        "vfs_init: per-fs init",
    )
    write(VFS, s)
    print("vfs_init: v250 changes applied")
else:
    print("vfs_init: already patched")

print("v250 patch applied")
