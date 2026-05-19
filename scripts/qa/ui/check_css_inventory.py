#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import argparse

def lines(p):
    return {x.strip() for x in Path(p).read_text(encoding="utf-8").splitlines() if x.strip() and not x.startswith("#")}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--expected", default="harness/quality/ui-css-files.expected.txt")
    args=ap.parse_args()
    expected=lines(args.expected)
    actual=set()
    p=Path("src/session_browser/web/static/style.css")
    if p.exists(): actual.add(str(p))
    cssdir=Path("src/session_browser/web/static/css")
    if cssdir.exists():
        for f in cssdir.glob("*.css"): actual.add(str(f))
    missing=sorted(expected-actual); extra=sorted(actual-expected)
    if missing or extra:
        print("FAIL: CSS inventory mismatch")
        if missing: print("missing:", *missing, sep="\n- ")
        if extra: print("extra:", *extra, sep="\n- ")
        return 1
    print("PASS: CSS inventory")
    return 0
if __name__=="__main__":
    raise SystemExit(main())
