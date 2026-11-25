#!/usr/bin/env python3
import os, sys
W=os.environ.get('XNU_WORK')
if not W: sys.exit('XNU_WORK not set')
p=os.path.join(W,'osfmk','arm64','sleh.c')
s=open(p,encoding='utf-8').read()
if 'v369 sp1 far' in s:
 print('v369: already applied'); raise SystemExit
old='''\t/* g0245d v352: the panic text does not fit on the console row, so a
\t * photo never shows the faulting address.  Trace the ESR and the FAR
\t * instead -- the FAR is the address that actually faulted. */
\t{ extern void g0245d_tracev(const char *, unsigned long long);
\t  g0245d_tracev("v352 esr", (unsigned long long)esr);
\t  g0245d_tracev("v352 far", (unsigned long long)(uintptr_t)far);
\t  g0245d_tracev("v352 pc", (unsigned long long)(uintptr_t)get_saved_state_pc(state)); }
'''
new='''\t{ extern void g0245d_tracev(const char *, unsigned long long);
\t  static unsigned int v369_once;
\t  if (!v369_once++) {
\t    g0245d_tracev("v369 sp1 esr", (unsigned long long)esr);
\t    g0245d_tracev("v369 sp1 far", (unsigned long long)(uintptr_t)far);
\t    g0245d_tracev("v369 sp1 pc", (unsigned long long)(uintptr_t)get_saved_state_pc(state));
\t  } }
'''
if s.count(old)!=1: sys.exit('v369: v352 SP1 anchor not found uniquely')
open(p,'w',encoding='utf-8').write(s.replace(old,new,1)); print('v369: SP1 capture installed')
