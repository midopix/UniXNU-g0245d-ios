#!/usr/bin/env python3
"""g0245d v275 -- bracket udp_init's tail and tcp_init end to end.

v274 boot picture decoded:
  * the "v274 hi caller 123828760" (low 32 bits of the caller RA) resolves
    in the unstripped kernel to _udp_init+0x90 -- udp_init's FIRST
    hashinit.  Both of udp_init's hashinits then succeeded
    ("hi alloc ret 0x..." twice, seq 8321 and 8326).
  * none of the v274 sleep probes (zwait kma/zba/elem, grab wait) fired,
    so the stall after seq 8326 is NOT a VM page sleep.
  * the INET protosw order is ip_init -> udp_init -> tcp_init, so the
    silence right after udp's second hashinit sits either in udp_init's
    tail (lck_grp_alloc_init / lck_rw_init / in_pcbinfo_attach) or in
    tcp_init (lck_grp, thread_call_allocate, tcp_cache_init which does
    two zalloc_permanent calls, MPKL log object).

v275 is again a pure observability release:

  1. uipc_domain.c: init_proto() and pr_init_old() log the protocol
     number before dispatching pr_init and a "done" after it returns --
     the photo will name the protocol whose init hangs (17=udp, 6=tcp).
  2. udp_usrreq.c: udp_init bracketed after hashinit #2, after the
     lock-group allocation and after in_pcbinfo_attach.
  3. tcp_subr.c: tcp_init bracketed at entry, after read_frandom,
     after tcp_tfo_init, after the tcppcb lock group, after
     thread_call_allocate, after tcp_cache_init and after the MPKL
     log object.
  4. tcp_cache.c: tcp_cache_init logs the rounded cache size and each
     of its two zalloc_permanent calls.
"""
import os
import sys

WORK = os.environ.get("XNU_WORK")
if not WORK:
    sys.exit("set XNU_WORK to the xnu-work tree")

UIPC = os.path.join(WORK, "bsd/kern/uipc_domain.c")
UDP = os.path.join(WORK, "bsd/netinet/udp_usrreq.c")
TCP = os.path.join(WORK, "bsd/netinet/tcp_subr.c")
TCACHE = os.path.join(WORK, "bsd/netinet/tcp_cache.c")

MARK = "g0245d v275"

DECL = ("extern void g0245d_trace(const char *);\n"
        "extern void g0245d_trace_u(const char *, unsigned int);\n")


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


# ------------------------------------------------------------ uipc_domain.c
s = read(UIPC)
if MARK not in s:
    s = sub(
        s,
        ("\t\tif (pp->pr_init != NULL) {\n"
         "\t\t\tpp->pr_init(pp, dp);\n"
         "\t\t}\n"),
        ("\t\tif (pp->pr_init != NULL) {\n"
         "\t\t\t/* g0245d v275: name the protocol whose init runs. */\n"
         "\t\t\t{ extern void g0245d_trace(const char *);\n"
         "\t\t\t  extern void g0245d_trace_u(const char *, unsigned int);\n"
         "\t\t\t  g0245d_trace_u(\"v275 prinit\", pp->pr_protocol); }\n"
         "\t\t\tpp->pr_init(pp, dp);\n"
         "\t\t\t{ extern void g0245d_trace(const char *);\n"
         "\t\t\t  g0245d_trace(\"v275 prinit done\"); }\n"
         "\t\t}\n"),
        "uipc_domain: init_proto bracketed",
    )
    s = sub(
        s,
        """	if (pp->pr_old->pr_init != NULL) {
		pp->pr_old->pr_init();
	}""",
        """	if (pp->pr_old->pr_init != NULL) {
		/* g0245d v275: name the legacy protocol too. */
		{ extern void g0245d_trace(const char *);
		  extern void g0245d_trace_u(const char *, unsigned int);
		  g0245d_trace_u("v275 prold", pp->pr_protocol); }
		pp->pr_old->pr_init();
		{ extern void g0245d_trace(const char *);
		  g0245d_trace("v275 prold done"); }
	}""",
        "uipc_domain: pr_init_old bracketed",
    )
    write(UIPC, s)
    print("uipc_domain.c: protocol dispatch traced")
else:
    print("uipc_domain.c: already patched")

# ------------------------------------------------------------- udp_usrreq.c
s = read(UDP)
if MARK not in s:
    s = sub(
        s,
        """	udbinfo.ipi_porthashbase = hashinit(UDBHASHSIZE, M_PCB,
	    &udbinfo.ipi_porthashmask);
	udbinfo.ipi_zone.zov_kt_heap = inpcbzone;""",
        """	udbinfo.ipi_porthashbase = hashinit(UDBHASHSIZE, M_PCB,
	    &udbinfo.ipi_porthashmask);
	/* g0245d v275: both hashinits already succeeded (v274 proof). */
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v275 udp hash2"); }
	udbinfo.ipi_zone.zov_kt_heap = inpcbzone;""",
        "udp: after hashinit #2",
    )
    s = sub(
        s,
        """	pcbinfo->ipi_lock_grp = lck_grp_alloc_init("udppcb",
	    LCK_GRP_ATTR_NULL);
	lck_attr_setdefault(&pcbinfo->ipi_lock_attr);""",
        """	pcbinfo->ipi_lock_grp = lck_grp_alloc_init("udppcb",
	    LCK_GRP_ATTR_NULL);
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v275 udp grp"); }
	lck_attr_setdefault(&pcbinfo->ipi_lock_attr);""",
        "udp: after lock group",
    )
    s = sub(
        s,
        """	udbinfo.ipi_gc = udp_gc;
	in_pcbinfo_attach(&udbinfo);
}""",
        """	udbinfo.ipi_gc = udp_gc;
	in_pcbinfo_attach(&udbinfo);
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v275 udp done"); }
}""",
        "udp: end of udp_init",
    )
    write(UDP, s)
    print("udp_usrreq.c: udp_init bracketed")
else:
    print("udp_usrreq.c: already patched")

# --------------------------------------------------------------- tcp_subr.c
s = read(TCP)
if MARK not in s:
    s = sub(
        s,
        """	tcp_initialized = 1;

#if DEBUG || DEVELOPMENT
	(void) PE_parse_boot_argn("tcp_rxt_seg_max", &tcp_rxt_seg_max,""",
        """	tcp_initialized = 1;
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v275 tcp enter"); }

#if DEBUG || DEVELOPMENT
	(void) PE_parse_boot_argn("tcp_rxt_seg_max", &tcp_rxt_seg_max,""",
        "tcp: entry",
    )
    s = sub(
        s,
        """	microuptime(&tcp_uptime);
	read_frandom(&tcp_now, sizeof(tcp_now));""",
        """	microuptime(&tcp_uptime);
	read_frandom(&tcp_now, sizeof(tcp_now));
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v275 tcp frnd"); }""",
        "tcp: after read_frandom",
    )
    s = sub(
        s,
        """	tcp_tfo_init();

	LIST_INIT(&tcb);""",
        """	tcp_tfo_init();
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v275 tcp tfo"); }

	LIST_INIT(&tcb);""",
        "tcp: after tfo_init",
    )
    s = sub(
        s,
        """	pcbinfo->ipi_lock_grp = lck_grp_alloc_init("tcppcb",
	    LCK_GRP_ATTR_NULL);
	lck_attr_setdefault(&pcbinfo->ipi_lock_attr);""",
        """	pcbinfo->ipi_lock_grp = lck_grp_alloc_init("tcppcb",
	    LCK_GRP_ATTR_NULL);
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v275 tcp grp"); }
	lck_attr_setdefault(&pcbinfo->ipi_lock_attr);""",
        "tcp: after tcppcb lock group",
    )
    s = sub(
        s,
        """	tcp_timer_list.call = thread_call_allocate(tcp_run_timerlist, NULL);
	if (tcp_timer_list.call == NULL) {
		panic("failed to allocate call entry 1 in tcp_init");
	}""",
        """	tcp_timer_list.call = thread_call_allocate(tcp_run_timerlist, NULL);
	if (tcp_timer_list.call == NULL) {
		panic("failed to allocate call entry 1 in tcp_init");
	}
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v275 tcp tcall"); }""",
        "tcp: after thread_call_allocate",
    )
    s = sub(
        s,
        """	/* Initialize TCP Cache */
	tcp_cache_init();""",
        """	/* Initialize TCP Cache */
	tcp_cache_init();
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v275 tcp cache"); }""",
        "tcp: after tcp_cache_init",
    )
    s = sub(
        s,
        """	tcp_mpkl_log_object = MPKL_CREATE_LOGOBJECT("com.apple.xnu.tcp");
	if (tcp_mpkl_log_object == NULL) {
		panic("MPKL_CREATE_LOGOBJECT failed");
	}""",
        """	tcp_mpkl_log_object = MPKL_CREATE_LOGOBJECT("com.apple.xnu.tcp");
	if (tcp_mpkl_log_object == NULL) {
		panic("MPKL_CREATE_LOGOBJECT failed");
	}
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v275 tcp mpkl"); }""",
        "tcp: after MPKL log object",
    )
    write(TCP, s)
    print("tcp_subr.c: tcp_init bracketed")
else:
    print("tcp_subr.c: already patched")

# -------------------------------------------------------------- tcp_cache.c
s = read(TCACHE)
if MARK not in s:
    s = sub(
        s,
        """	tcp_cache = zalloc_permanent(sizeof(struct tcp_cache_head) * tcp_cache_size,
	    ZALIGN(struct tcp_cache_head));""",
        """	{ extern void g0245d_trace(const char *);
	  extern void g0245d_trace_u(const char *, unsigned int);
	  g0245d_trace_u("v275 tcpc size", tcp_cache_size); }
	tcp_cache = zalloc_permanent(sizeof(struct tcp_cache_head) * tcp_cache_size,
	    ZALIGN(struct tcp_cache_head));
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v275 tcpc z1"); }""",
        "tcp_cache: after cache table alloc",
    )
    s = sub(
        s,
        """	tcp_heuristics = zalloc_permanent(sizeof(struct tcp_heuristics_head) * tcp_cache_size,
	    ZALIGN(struct tcp_heuristics_head));""",
        """	tcp_heuristics = zalloc_permanent(sizeof(struct tcp_heuristics_head) * tcp_cache_size,
	    ZALIGN(struct tcp_heuristics_head));
	{ extern void g0245d_trace(const char *);
	  g0245d_trace("v275 tcpc z2"); }""",
        "tcp_cache: after heuristics alloc",
    )
    write(TCACHE, s)
    print("tcp_cache.c: tcp_cache_init bracketed")
else:
    print("tcp_cache.c: already patched")

print("v275 done")
