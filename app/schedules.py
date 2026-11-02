"""Schedule lists (doors / aluminium / frames): parse the list sheet, count its tags on the plan sheets, return BOQ lines.
A tag on the plan that is missing from the list (or a list row never seen on the plan) becomes a warning."""
import re, pymupdf
_c=lambda t:re.sub(r'[‎‏‪-‮]','',t)
KIND={'door_schedule':dict(prefix='דנ',ch=6,sub=1,desc='דלתות פנים',unit="יח'",label='דלת נגרות'),
      'window_schedule':dict(prefix='אל',ch=12,sub=1,desc='דלתות ותריסי אלומיניום',unit="יח'",label='אלומיניום'),
      'frames_schedule':dict(prefix='M',ch=6,sub=3,desc='דלתות פח עם משקוף מגולוון',unit="יח'",label='מסגרות')}

def _rows(pg):
    rows={}
    for w in pg.get_text('words'): rows.setdefault(round(w[1]/4),[]).append((w[0],_c(w[4])))
    return [[t for x,t in sorted(rows[y],reverse=True)] for y in sorted(rows)]

def parse(path,kind):
    """-> list of dict(tag,num,desc,size) read from the first page of a schedule sheet"""
    pre=KIND[kind]['prefix']; out=[]
    pg=pymupdf.open(path)[0]; rows=_rows(pg)
    for i,r in enumerate(rows):
        if len(r)>=3 and r[0]==pre and re.fullmatch(r'\d+',r[1]):
            rest=r[2:]; sizes=[t for t in rest if re.fullmatch(r'\d{2,3}(/\d{2,3})?',t)]
            desc=' '.join(t for t in rest if t not in sizes)
            if kind=='door_schedule' and len(sizes)>=2: size=f'{sizes[0]}/{sizes[1]}'
            else: size=next((s for s in sizes if '/' in s),'')
            out.append(dict(tag=pre,num=int(r[1]),desc=desc,size=size))
    # a row that continues on the next visual line (size only)
    return out

def count_tags(plan_paths,prefix,known=()):
    """how many times each tag number appears next to the tag prefix on the plan sheets"""
    cnt={}
    for p in plan_paths:
        pg=pymupdf.open(p)[0]; W=[(w[0],w[1],_c(w[4])) for w in pg.get_text('words')]
        for x,y,t in W:
            if t!=prefix: continue
            near=[(abs(x2-x),t2) for x2,y2,t2 in W if abs(y2-y)<14 and 0<abs(x2-x)<45 and re.fullmatch(r'\d{1,2}',t2)]
            ok=[q for q in near if int(q[1]) in known]
            if ok: n=int(min(ok)[1]); cnt[n]=cnt.get(n,0)+1
            elif near:
                d,t2=min(near)
                if d<25: n=int(t2); cnt[n]=cnt.get(n,0)+1
    return cnt

def lines(sheets,path_of):
    """sheets: project sheets; returns (lines, warnings, info)"""
    L=[]; warn=[]; info={}
    plans=[path_of(s) for s in sheets if s['type'] in('floor_plan','layout','demolition','flooring','ceiling')]
    # use the construction/layout plans only for door/window tags
    base=[path_of(s) for s in sheets if s['type']=='floor_plan'] or plans
    for s in sheets:
        k=s['type']
        if k not in KIND: continue
        K=KIND[k]; rows=parse(path_of(s),k)
        if not rows: warn.append(dict(t=f'לא נקראו שורות מהרשימה "{s["file"]}"',why='פורמט הרשימה לא זוהה',how='אשר ידנית')); continue
        cnt=count_tags(base,K['prefix'],{r['num'] for r in rows}) if base else {}
        total=sum(cnt.get(r['num'],0) for r in rows)
        info[k]=dict(rows=len(rows),counted=total,unlisted=sorted(n for n in cnt if n not in {r['num'] for r in rows}))
        det=', '.join(f"{K['prefix']}-{r['num']} {r['size']} ×{cnt.get(r['num'],0)}".strip() for r in rows)
        if base and total:
            L.append(dict(ch=K['ch'],sub=K['sub'],desc=K['desc'],unit=K['unit'],q=float(total),st='נמדד',src=f"רשימת {K['label']} + ספירת תגיות בתוכנית ({det})",need='',cover=[K['desc']]))
        else:
            L.append(dict(ch=K['ch'],sub=K['sub'],desc=K['desc'],unit=K['unit'],q=None,st='דורש השלמה',src=f"רשימת {K['label']}: {len(rows)} סוגים. לא נמצאו תגיות בתוכנית",need='תוכנית בניה עם תגיות פתחים',cover=[K['desc']]))
        for r in rows:
            if base and cnt.get(r['num'],0)==0: warn.append(dict(t=f"ברשימת {K['label']}: {K['prefix']}-{r['num']} לא נמצא בתוכנית",why='סוג ברשימה שלא סומן באף מקום בתוכנית',how='בדוק אם חסר תיוג או שהסוג מיותר'))
        for n in info[k]['unlisted']: warn.append(dict(t=f"בתוכנית יש תגית {K['prefix']}-{n} שאינה ברשימת {K['label']}",why='תגית ללא שורה ברשימה: חסר סוג ברשימה',how='הוסף את הסוג לרשימה או תקן את התגית'))
    return L,warn,info
