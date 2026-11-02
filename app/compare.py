"""Compare our BOQ with a reference BOQ by CONCEPT (project independent): both sides are mapped to concepts by Hebrew keywords,
quantities of the same concept+unit are summed and compared."""
import re
CONCEPTS=[
 ('פירוק והריסה',r'^פירוק|^הריסת|הריסות'),
 ('דלתות נגרות',r'^(נגיש - )?דלת עם מילוי|^דלתות פנים|דלת נגרות'),('דלתות פלדה ופח',r'דלת.*(פלדה|פח)|דלתות ותריסי? .*פלדה|פח מגולוון.*דלת'),('משקופים',r'משקוף'),
 ('חלונות ואלומיניום',r'^(חלון|תריס|דלתות ותריסי|ציפוי ביטחון|מנוע חשמלי לתריס)'),('ריצוף אריחים',r'ריצוף.*(גרניט|פורצלן|אריח)'),('אפוקסי',r'אפוקסי'),
 ('תקרות גבס',r'תקרת גבס|תקרות גבס'),('תקרות אקוסטיות',r'^תקר(ה|ות).*אקוסטי'),('תקרות מגשי פח',r'מגשי'),('סינר/גליף',r'סינר|גליף'),
 ('מחיצות גבס',r'מחיצות גבס'),('חיפוי גבס',r'חיפוי.*גבס'),('צבע',r'^צבע|סופרקריל'),
 ('משטחי בטון',r'מרצפי בטון|משטחי בטון'),('שיפולים',r'שיפולים|סוקל'),
]
def concept(desc):
    d=desc.strip()
    if d.startswith('תוספת'): return None
    for name,rx in CONCEPTS:
        if re.search(rx,d): return name
    return None

def aggregate(items):
    """items: iterable of (desc,unit,qty) -> {(concept,unit):qty}"""
    out={}
    for d,u,q in items:
        if q is None: continue
        c=concept(d)
        if c: out[(c,u)]=out.get((c,u),0)+q
    return out

def compare(ref,ours):
    """-> list of dict(concept,unit,ref,ours,dev,status); status: 'תואם' (<=5%), 'קרוב' (<=15%), 'סטייה', 'חסר אצלנו', 'רק אצלנו'"""
    R=aggregate(ref); O=aggregate(ours); rows=[]
    for k in sorted(set(R)|set(O)):
        r=R.get(k); o=O.get(k)
        if r and o: dev=(o-r)/r*100; st='תואם' if abs(dev)<=5 else 'קרוב' if abs(dev)<=15 else 'סטייה'
        elif r: dev=None; st='חסר אצלנו'
        else: dev=None; st='רק אצלנו'
        rows.append(dict(concept=k[0],unit=k[1],ref=r,ours=o,dev=dev,status=st))
    return rows
