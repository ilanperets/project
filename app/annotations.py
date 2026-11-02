"""Quantities and notes written on the plans themselves (legend tables, finish schedules, general notes).
Principle: architects often state "NNN m² <finish>" in a legend. We read every such statement on every plan sheet,
classify it by keywords (not by file or project), and emit BOQ lines; general notes are surfaced as 'what to watch'."""
import re, pymupdf
_c=lambda t:re.sub(r'[‎‏‪-‮]','',t)
QTY=re.compile(r'(\d[\d,]*(?:\.\d+)?)\s*(m²|m2|מ"ר|מ"א|מ\'|יח\')\s*(.+?)(?=(?:\d[\d,]*(?:\.\d+)?\s*(?:m²|m2|מ"ר))|$)',re.S)
UNIT={'m²':'מ"ר','m2':'מ"ר','מ"ר':'מ"ר','מ"א':'מ"א',"מ'":'מ"א',"יח'":"יח'"}
# keyword -> (chapter, sub, spec-style description)
RULES=[
 (r'אפוקסי',(10,3,'צבע אפוקסי דו רכיבי על רצפות ומדרגות בטון, כולל פנלים')),
 (r'מגשי',(22,2,'תקרת מגשי פח מגולוון מחוררים')),
 (r'אקוסטי|מינרל|Advantage|מונחת',(22,2,'תקרה אקוסטית מאריחים מינרליים מודולריים')),
 (r'סינר',(22,1,'סינר גבס צבוע')),
 (r'תקרת גבס|תקרות גבס|תקרה.*גבס',(22,1,'תקרת גבס צבועה')),
 (r'גרניט|פורצלן|קרמיקה|אריח|ריצוף',(10,1,'ריצוף באריחי גרניט פורצלן, כולל פנלים')),
 (r'פרקט|למינציה',(10,1,'ריצוף פרקט או למינציה')),
 (r'מחיצ',(22,1,'מחיצות גבס')),
 (r'צבע|סופרקריל',(11,1,'צבע על טיח או גבס')),
]
NOTE=re.compile(r'^(הערות?|הערה|יש |כל |קירות? |אין |יחופו|חובה|בכפוף|לאשר|לתאם)')

def scan(path):
    pg=pymupdf.open(path)[0]; q=[]; notes=[]
    for b in pg.get_text('blocks'):
        t=' '.join(_c(b[4]).split())
        if not t: continue
        for m in QTY.finditer(t):
            val=float(m.group(1).replace(',','')); u=UNIT.get(m.group(2)); d=m.group(3).strip(' .,')
            if val<=0 or not u or len(d)<4: continue
            q.append(dict(q=val,unit=u,text=d[:140]))
        if len(t)>25 and NOTE.match(t) : notes.append(t[:200])
    return q,notes

def lines(sheets,path_of):
    L=[]; notes=[]; seen=set()
    for s in sheets:
        if s['type'] in('door_schedule','window_schedule','frames_schedule','sheet_index'): continue
        try: qs,ns=scan(path_of(s))
        except Exception: continue
        notes+=[dict(sheet=s['file'],text=n) for n in ns]
        for x in qs:
            if x['unit']!='מ"ר' : continue
            for rx,(ch,sub,desc) in RULES:
                if re.search(rx,x['text']):
                    k=(ch,desc,x['q'])
                    if k in seen: break
                    seen.add(k)
                    L.append(dict(ch=ch,sub=sub,desc=desc,unit='מ"ר',q=x['q'],st='נמדד',src=f"כמות כתובה בטבלה בתוכנית: \"{x['text'][:60]}\" ({s['file'][:18]})",need='לאמת מול מדידה בתוכנית',cover=[desc]))
                    break
    return L,notes
