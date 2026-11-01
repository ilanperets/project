"""Readiness scorecard of a calculated project: how much of the bill is measured, estimated, or missing, and why."""
import re


def score(boq):
    its = [r for r in (boq or []) if r.get('kind') == 'item']
    n = len(its)
    if not n: return dict(items=0)
    got = [r for r in its if r.get('q') is not None]
    firm = [r for r in got if r.get('st') in ('נמדד', 'ידני')]
    est = [r for r in got if r.get('st') not in ('נמדד', 'ידני')]
    miss = [r for r in its if r.get('q') is None]
    gaps = {}
    for r in miss:
        need = r.get('need') or ''
        m = re.match(r'חסר גיליון מסוג "([^"]+)"', need)
        if m: key = ('sheet', 'חסר גיליון: ' + m.group(1))
        else:
            m = re.match(r'יש גיליון מסוג "([^"]+)"', need)
            key = ('engine', 'אין עדיין מנוע: ' + m.group(1)) if m else ('input', 'דורש הזנה או מדידה ידנית')
        g = gaps.setdefault(key[1], dict(kind=key[0], label=key[1], n=0)); g['n'] += 1
    no_sheet = sum(g['n'] for g in gaps.values() if g['kind'] == 'sheet')
    supported = n - no_sheet
    pct = lambda a, b: round(100 * a / b) if b else 0
    return dict(items=n, measured=len(firm), estimated=len(est), missing=len(miss), missing_no_sheet=no_sheet,
                coverage_all=pct(len(got), n),                 # any quantity at all, out of all items
                coverage_supported=pct(len(got), supported),   # out of items the uploaded sheets could support
                firm_share=pct(len(firm), supported),          # measured directly or entered by the user
                gaps=sorted(gaps.values(), key=lambda g: -g['n'])[:10])
