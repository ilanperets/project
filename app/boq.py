"""Builds a hierarchical BOQ (NN.00.0000 chapter / NN.SS.0000 sub / NN.SS.IIII item) from engine lines,
adds the items every project is expected to have (missing ones stay without quantity), and lists what the brain needs."""
import datetime, openpyxl, openpyxl.worksheet.properties
from openpyxl.styles import Font, PatternFill, Alignment
from .classify import TYPES

from .spec import SPEC, CHAPTERS as CH
from .brain import toks
SUB={(2,2):'תבניות וזיון',(4,2):'אלמנטים משולבים',(6,2):'מעקות ומסגרות',(7,2):'צנרת',(8,2):'תעלות וכבלים',(8,3):'לוחות',(10,2):'חיפוי קירות',(40,2):'אדמה וגינון'}
def _sub(ch,sub): return SUB.get((ch,sub),'סעיפים ראשיים' if sub==1 else 'סעיפים נוספים')
EXPECTED=[(s['ch'],s['sub'],s['desc'],s['unit'],s['plan'],'לקבלת הכמות: '+s['method'],s) for s in SPEC]
BUILT={'foundation_piles','floor_plan','elevation','electrical'}
def _spec_for(ch,desc,unit):
    T=toks(desc);best=None
    for s in SPEC:
        if s['ch']!=ch: continue
        j=len(T&toks(s['desc']))/max(len(T|toks(s['desc'])),1)+(0.15 if s['unit']==unit else 0)
        if not best or j>best[0]: best=(j,s)
    return best[1] if best and best[0]>=0.15 else None   # types that have an engine today

def build(name,lines,present_types,ov=None,hidden=(),chnames=None):
    ov=ov or {}; CHN=dict(CH); CHN.update({int(k):v for k,v in (chnames or {}).items()})
    items={}   # (ch,sub) -> list of dict
    for l in lines:
        sp=_spec_for(l['ch'],l['desc'],l['unit']); l['method']=sp['method'] if sp else ''; l['vsrc']=sp['src'] if sp else ''
    for l in lines: items.setdefault((l['ch'],l.get('sub',1)),[]).append(dict(desc=l['desc'],unit=l['unit'],q=l['q'],st=l['st'],src=l['src'],need=l.get('need',''),method=l.get('method',''),vsrc=l.get('vsrc','')))
    have={l['ch'] for l in lines}
    for ch,sub,desc,unit,typ,need,sp in EXPECTED:
        if sp['eng'] and ch in have: continue
        if typ in present_types: why=f'יש גיליון מסוג "{TYPES[typ]}", המנוע לסוג זה טרם נבנה' if typ not in BUILT else need
        else: why=f'חסר גיליון מסוג "{TYPES[typ]}". {need}'
        items.setdefault((ch,sub),[]).append(dict(desc=desc,unit=unit,q=None,st='דורש השלמה',src=TYPES[typ],need=why,method=sp['method'],vsrc=sp['src']))
    for k in list(items):
        its=[]
        for it in items[k]:
            if it['desc'] in hidden: continue
            if it['desc'] in ov and ov[it['desc']] is not None: it=dict(it,q=ov[it['desc']],st='ידני',src='הוזן ידנית',need='')
            its.append(it)
        if its: items[k]=its
        else: del items[k]
    rows=[dict(kind='ch',code='00.00.0000',desc=name)]
    for ch in sorted({k[0] for k in items}):
        rows.append(dict(kind='ch',code=f'{ch:02d}.00.0000',desc=CHN.get(ch,f'פרק {ch}')))
        for sub in sorted(k[1] for k in items if k[0]==ch):
            rows.append(dict(kind='sub',code=f'{ch:02d}.{sub:02d}.0000',desc=_sub(ch,sub)))
            for i,it in enumerate(items[(ch,sub)],1):
                rows.append(dict(kind='item',code=f'{ch:02d}.{sub:02d}.{i*10:04d}',desc=it['desc'],unit=it['unit'],q=it['q'],src=f"{it['st']} · {it['src']}",need=it['need'],st=it['st'],method=it.get('method',''),vsrc=it.get('vsrc','')))
    return rows

def needs(sheets,missing_types,unbuilt_types,assumptions):
    out=[]
    for t in missing_types:
        out.append(dict(p='high',t=f'גיליון מסוג: {TYPES[t]}',why='לא נמצא בתיק, ולכן הסעיפים התלויים בו נשארו בלי כמות',gives='ראה סעיפים עם "חסר גיליון"',how='העלה את הגיליון'))
    for t in unbuilt_types:
        out.append(dict(p='med',t=f'מנוע חישוב ל: {TYPES[t]}',why='הגיליון זוהה, אבל המנוע לסוג הזה עוד לא נבנה, או שדרוש תיוג ממך',gives='סעיפים תלויים',how='שלח דוגמה לאימון המנוע, או הזן כמויות ידנית'))
    for a in assumptions: out.append(dict(p='med',t=a['t'],why=a['why'],gives=a.get('gives','דיוק הכמויות'),how=a['how']))
    return out

def to_xlsx(rows,name,path,needs_list=(),prices=None):
    prices=prices or {}
    NF='#,###,##0.00;[Red]\\-#,###,##0.00'; F=lambda **k:Font(name='Arial',size=k.pop('size',11),**k)
    HF=PatternFill('solid',fgColor='D9D9D9'); MISS=PatternFill('solid',fgColor='FDE2E2'); PART=PatternFill('solid',fgColor='FFF4D1'); CHF=PatternFill('solid',fgColor='EEF3FA')
    wb=openpyxl.Workbook(); a=wb.active; a.title='יצוא כתב כמויות'; a.sheet_view.rightToLeft=True
    a.append(['מספר','תאור',"יח' מידה",'כמות','מחיר קבלן','סה"כ קבלן','מחיר רום','סה"כ רום','הערות '])
    for c in a[1]: c.font=F(bold=True); c.fill=HF; c.alignment=Alignment(horizontal='center',wrap_text=True)
    t=wb.create_sheet('תמחור'); t.sheet_view.rightToLeft=True
    t['G9']=datetime.date.today(); t['G9'].number_format='dd/mm/yyyy'; t['A11']='הצעת מחיר - '+name; t['A11'].font=F(bold=True,size=18); t.merge_cells('A11:G12')
    for i,h in enumerate(['מספר','תאור',"יח' מידה",'כמות','מחיר','סה"כ','הערות (מקור המחיר) '],1):
        c=t.cell(15,i,h); c.font=F(bold=True); c.fill=HF
    r2=16
    for r in rows:
        k=r['kind']; ra=a.max_row+1
        if k in('ch','sub'):
            a.append([r['code'],r['desc']]); t.cell(r2,1,r['code']); t.cell(r2,2,r['desc'])
            for ws,rr in ((a,ra),(t,r2)):
                for c in ws[rr]: c.font=F(bold=True)
                if k=='ch':
                    for c in ws[rr]: c.fill=CHF
        else:
            pz=prices.get(r['code'],0)
            a.append([r['code'],r['desc'],' '+r['unit'],r['q'],pz,f'=E{ra}*D{ra}',0,f'=G{ra}*D{ra}',r['src']+(f" · חסר: {r['need']}" if r.get('need') else '')])
            t.cell(r2,1,r['code']); t.cell(r2,2,r['desc']); t.cell(r2,3,' '+r['unit']); t.cell(r2,4,r['q']); t.cell(r2,5,prices.get(r['code'],0)); t.cell(r2,6,f'=E{r2}*D{r2}')
            for col in (5,6,7,8): a.cell(ra,col).number_format=NF
            for col in (5,6): t.cell(r2,col).number_format=NF
            for ws,rr in ((a,ra),(t,r2)): ws.cell(rr,2).alignment=Alignment(wrap_text=True,vertical='top')
            fill=MISS if r['q'] is None else (PART if r.get('st')=='חלקי' else None)
            if fill: a.cell(ra,4).fill=fill; t.cell(r2,4).fill=fill
        r2+=1
    t.cell(r2,2,'סה"כ').font=F(bold=True); t.cell(r2,6,f'=SUM(F16:F{r2-1})').font=F(bold=True); t.cell(r2,6).number_format=NF
    for ws,w in ((a,[10.8,60.8,9.5,9.1,10.9,12.4,11.8,12.4,41.1]),(t,[10.8,60.8,9.6,9.1,11.8,12.4,41.1])):
        for col,x in zip('ABCDEFGHI',w): ws.column_dimensions[col].width=x
    for ws in (a,t):
        ws.page_setup.orientation='landscape'; ws.page_setup.fitToWidth=1; ws.page_setup.fitToHeight=0; ws.sheet_properties.pageSetUpPr=openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)
    a.freeze_panes='A2'; t.freeze_panes='A16'
    m=wb.create_sheet('מה חסר למערכת'); m.sheet_view.rightToLeft=True; m.append(['דחיפות','מה חסר','למה','מה זה משחרר','מה לעשות'])
    P={'high':'דחוף','med':'חשוב','low':'כשיהיה זמן'}
    for n in needs_list: m.append([P[n['p']],n['t'],n['why'],n['gives'],n['how']])
    for col,w in zip('ABCDE',[12,45,60,28,36]): m.column_dimensions[col].width=w
    wb.save(path)
