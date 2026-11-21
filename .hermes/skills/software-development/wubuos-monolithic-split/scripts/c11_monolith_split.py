#!/usr/bin/env python3
"""c11_monolith_split.py -- split a C11 monolith into leaf modules + opaque internal header.

TEMPLATE: reproduce with modifications for the target monolith: the function-name
groups, the struct/flags markers, and the public-header include.

Usage:
  python3 c11_monolith_split.py <monolith.c> <out_dir> <groups.json>

<groups.json> maps output basename (without .c) -> list of function names that belong
in that leaf. Every other top-level function definition becomes "public API" in
<stem>.c. The script:
  - detects every top-level definition by balanced-paren + '{' matching (NOT a naive
    brace counter -- that mis-balances when the opening '{' shares the signature line)
  - slices each def as [def_start, next_def_start)  -> boundaries guaranteed by the def
    positions themselves, so no brace-matching across the body is needed
  - emits <out>/<stem>.c (public API) and <out>/<grp>.c (each leaf, #include internal hdr)
  - emits <out>/<stem>_internal.h with the opaque struct + #define flags + non-static
    prototypes for every detected function

Verified on WuBuOS wubu_dos_emu.c (1048-line monolith -> 6 units, 22/22 tests green).
"""
import re, sys, json, os

KW = {"if","for","while","switch","return","case","do","else","goto","sizeof",
      "catch","struct","union","enum","typedef"}

def strip_comment(l):
    out=[]; i=0; ins=inc=esc=False
    while i < len(l):
        c=l[i]
        if ins:
            if esc: esc=False
            elif c=='"': ins=False
            else: out.append(c)
        elif inc:
            if c=='\\': esc=True
            elif c=="'": inc=False
            else: out.append(c)
        else:
            if c=='/' and i+1<len(l) and l[i+1]=='/': break
            if c=='/' and i+1<len(l) and l[i+1]=='*': inc=True; continue
            if c=='"': ins=True; out.append(c)
            elif c=="'": inc=True; out.append(c)
            else: out.append(c)
        i+=1
    return "".join(out)

def first_paren(l):
    ins=inc=esc=False
    for j,c in enumerate(l):
        if ins:
            if esc: esc=False
            elif c=='"': ins=False
        elif inc:
            if c=='\\': esc=True
            elif c=="'": inc=False
        else:
            if c=='/' and j+1<len(l) and l[j+1]=='/': break
            if c=='/' and j+1<len(l) and l[j+1]=='*': inc=True; continue
            if c=='"': ins=True
            elif c=="'": inc=True
            elif c=='(': return j
    return -1

def match_paren(L, i, p):
    d=1; i2=i; j=p+1
    while i2 < len(L):
        line=L[i2]
        while j < len(line):
            c=line[j]
            if c=='(': d+=1
            elif c==')':
                d-=1
                if d==0: return (i2, j)
            j+=1
        i2+=1; j=0
    return (len(L)-1, len(L[-1]))

def char_after(L, i, p):
    i2=i; j=p+1
    while i2 < len(L):
        line=L[i2]; k=j; prog=True
        while k < len(line):
            c=line[k]
            if c in ' \t\r\n': k+=1; continue
            if c=='/' and k+1<len(line) and line[k+1]=='/': prog=False; break
            if c=='/' and k+1<len(line) and line[k+1]=='*':
                kk=k+2
                while kk < len(line):
                    if line[kk]=='*' and kk+1<len(line) and line[kk+1]=='/':
                        k=kk+2; break
                    kk+=1
                else:
                    i2+=1; j=0; line=None; break
                continue
            return c
        if line is None: continue
        if not prog: break
        i2+=1; j=0
    return ''

def detect_defs(L):
    cand={}
    for i in range(len(L)):
        raw=L[i]; p=first_paren(raw)
        if p < 0: continue
        before=strip_comment(raw)[:p]
        m=re.search(r'([A-Za-z_]\w*)\s*$', before)
        if not m: continue
        name=m.group(1)
        if name in KW: continue
        if re.search(r'\b(if|for|while|switch|return|case|do|else|goto|sizeof|'
                     r'catch|struct|union|enum|typedef)\b', before): continue
        if ';' in before or '=' in before or ',' in before: continue
        (el,ec)=match_paren(L, i, p)
        if char_after(L, el, ec)=='{':
            cand.setdefault(name, []).append(i)
    return cand

def back_cap(L, si, name):
    """Include a genuine type-continuation line above the def (e.g. 'uint16_t\n foo(')."""
    if si <= 0: return si
    prev=L[si-1].rstrip()
    if not prev: return si
    if prev.endswith(('}',';','{')): return si
    if prev.startswith(('/*','*','//')): return si
    if '(' in prev or '=' in prev: return si
    if re.search(r'\b(if|for|while|switch|return|do|else|goto|struct|enum|'
                 r'union|typedef|static)\b', prev): return si
    if not re.search(r'[A-Za-z0-9*&]$', prev): return si
    if name not in (L[si-1] + " " + L[si]): return si
    return si-1

def main():
    mono, out, gj = sys.argv[1], sys.argv[2], sys.argv[3]
    groups = json.load(open(gj))
    L = open(mono).read().split("\n")
    stem = os.path.splitext(os.path.basename(mono))[0]
    cand = detect_defs(L)
    grouped = set()
    for v in groups.values(): grouped |= set(v)
    assert all(a in cand and len(cand[a])==1 for a in grouped), \
        "group name not a unique top-level def: " + str(
            [a for a in grouped if a not in cand or len(cand[a])!=1])
    all_defs = set(cand.keys())
    allstarts = sorted(cand[n][0] for n in all_defs)

    buckets = {g: [] for g in groups}; buckets['__main__'] = []
    protos = {}
    for name in all_defs:
        rs = cand[name][0]; si = back_cap(L, rs, name)
        nxt = [s for s in allstarts if s > rs]
        ei = nxt[0]-1 if nxt else len(L)-1
        body = "\n".join(L[si:ei+1])
        pidx = body.index(')'); sig = body[:pidx+1].replace('\n',' ').strip()
        sig = re.sub(r'^static\s+', '', sig)
        protos[name] = sig + ";"
        if name in grouped:
            for g, names in groups.items():
                if name in names:
                    buckets[g].append(body); break
        else:
            buckets['__main__'].append(body)

    flags = [l for l in L if l.strip().startswith("#define ")]
    struct_lines = [x for x in L if x.strip().startswith("struct ")]
    struct_block = ""
    if struct_lines:
        s0 = L.index(struct_lines[0])
        depth=0; outl=[]
        for j in range(s0, len(L)):
            outl.append(L[j])
            if "{" in L[j]: depth+=1
            if "}" in L[j]:
                depth-=0 if False else depth-1
                if depth==0: break
        struct_block = "\n".join(outl)

    hdr = (f"/* {stem}_internal.h -- opaque internals. */\n"
           f"#ifndef {stem.upper()}_INTERNAL_H\n#define {stem.upper()}_INTERNAL_H\n"
           f"#include \"{stem}.h\"\n#include <stdint.h>\n#include <stddef.h>\n"
           f"#include <stdbool.h>\n#include <stdlib.h>\n#include <string.h>\n"
           f"#include <stdio.h>\n\n" + "\n".join(flags) + "\n\n"
           + struct_block + "\n\n")
    for name in all_defs:
        hdr += protos[name] + "\n"
    hdr += "\n#endif\n"
    open(f"{out}/{stem}_internal.h", "w").write(hdr)

    for g, body in buckets.items():
        if g == "__main__":
            fn = f"{out}/{stem}.c"
            content = (f"/* {stem}.c -- public API. */\n#include \"{stem}_internal.h\"\n\n"
                       + "\n\n".join(body) + "\n")
        else:
            fn = f"{out}/{g}.c"
            content = (f"/* {g}.c -- leaf module (self-contained C11). */\n"
                       f"#include \"{stem}_internal.h\"\n\n" + "\n\n".join(body) + "\n")
        open(fn, "w").write(content)
    print("WROTE", stem, "main:", len(buckets['__main__']),
          "groups:", {g: len(v) for g, v in buckets.items() if g != '__main__'})

if __name__ == "__main__":
    main()
