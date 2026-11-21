#!/usr/bin/env python3
"""review_1000.py -- generate the idempotent 1000-pass review packs."""
import argparse, json, os, sys

PHASES = ["Locate", "Argue AGAINST", "Argue FOR", "Decide"]
STATUS = ["pending", "running", "done", "skipped", "failed"]

TEMPLATE = """### Pass {pid:04d} — {phase}
- Claim:
- Evidence (command + real output):
- Negative control (pre-fix / forced failure):
- FOR case (strongest):
- AGAINST case (strongest):
- Decision:
- STATUS: {status}
"""

PACK_TEMPLATE = """# Review pack {pack:03d}

Passes {first:04d}-{last:04d} of {total:04d}. Four phases per pass.

{passes}
"""


def main():
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--root", default=os.path.dirname(here))
    ap.add_argument("--passes", type=int, default=1000)
    ap.add_argument("--pack-size", type=int, default=4)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    if args.passes % args.pack_size:
        print("ERROR: --passes must be divisible by --pack-size", file=sys.stderr)
        return 2
    out_dir = os.path.join(args.root, "sessions", "review-1000")
    os.makedirs(out_dir, exist_ok=True)

    packs = args.passes // args.pack_size
    state = {
        "passes": args.passes, "packs": packs,
        "phases_per_pass": len(PHASES), "phase_steps": args.passes * len(PHASES),
        "pack_size": args.pack_size, "status_codes": STATUS, "items": [],
    }
    written = []
    for pack in range(1, packs + 1):
        first = (pack - 1) * args.pack_size + 1
        last = first + args.pack_size - 1
        body, items = [], []
        for pid in range(first, last + 1):
            for phase in PHASES:
                body.append(TEMPLATE.format(pid=pid, phase=phase,
                                            status=STATUS[0]))
                items.append({"pass": pid, "phase": phase, "status": STATUS[0]})
        text = PACK_TEMPLATE.format(pack=pack, first=first, last=last,
                                    total=args.passes, passes="\n".join(body))
        p = os.path.join(out_dir, f"pack-{pack:03d}.md")
        if args.write:
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            written.append(p)
        state["items"].append({"pack": pack, "first": first, "last": last,
                               "phases": items})
    if args.write:
        with open(os.path.join(out_dir, "review-state.json"), "w",
                  encoding="utf-8", newline="\n") as f:
            json.dump(state, f, indent=2)
        with open(os.path.join(out_dir, "REVIEW.md"), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(f"# 1000-pass review state\n\n"
                    f"- passes: {args.passes}\n- packs: {packs}\n"
                    f"- phases/pass: {len(PHASES)}\n"
                    f"- phase steps: {state['phase_steps']}\n"
                    f"- generated packs: {len(written)}\n")
    print(f"review_1000: passes={args.passes} packs={packs} "
          f"phases={state['phase_steps']} written={len(written)} dir={out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
