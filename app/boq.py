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
    covered={l['desc'] for l in lines}
    for l in lines: covered.update(l.get('cover') or [])
    for pre,L in (('קירות',['קירות בלוקים בעובי 10 ס"מ','קירות בלוקים בעובי 15 ס"מ','קירות בלוקים בעובי 20 ס"מ']),):
        if any(l['desc'].startswith(pre) and l['ch']==4 for l in lines): covered.update(L)
    if any(l['ch']==5 and l['desc'].startswith('איטום גג') for l in lines): covered.add('איטום גגות ומרפסות')
    if any(l['ch']==10 and l['desc'].startswith('ריצוף') for l in lines): covered.add('ריצוף אריחים')
    if any(l['ch']==23 and 'כלונסאות' in l['desc'] for l in lines): covered.add('כלונסאות קדוחים ויצוקים באתר')
    for ch,sub,desc,unit,typ,need,sp in EXPECTED:
        if desc in covered: continue
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

def to_xlsx(rows,name,path,needs_list=(),prices=None,meta=None):
    meta=meta or {}
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

    # ---- cover, chapter summary, methods ----
    from openpyxl.styles import Border, Side
    DK=PatternFill('solid',fgColor='0D43A0'); LN=Side(style='thin',color='D0D7E2')
    items=[r for r in rows if r['kind']=='item']; nq=sum(1 for r in items if r['q'] is not None)
    npart=sum(1 for r in items if r.get('st')=='חלקי'); nman=sum(1 for r in items if r.get('st')=='ידני')
    cv=wb.create_sheet('שער',0); cv.sheet_view.rightToLeft=True; cv.sheet_view.showGridLines=False
    for col,w in zip('ABCD',[4,26,40,24]): cv.column_dimensions[col].width=w
    cv['B3']='כתב כמויות'; cv['B3'].font=F(bold=True,size=28,color='0D43A0'); cv.merge_cells('B3:D3')
    cv['B4']=name; cv['B4'].font=F(bold=True,size=16); cv.merge_cells('B4:D4')
    info=[('לקוח',meta.get('client','')),('גרסה',meta.get('version','')),('תאריך',datetime.date.today().strftime('%d/%m/%Y')),('מודד',meta.get('measurer','')),('בודק',meta.get('reviewer','')),('סטטוס',{'received':'התקבל','measuring':'במדידה','review':'בבדיקה','delivered':'נמסר'}.get(meta.get('status',''),meta.get('status','')))]
    for i,(k,v) in enumerate(info):
        r=6+i; cv.cell(r,2,k).font=F(bold=True,color='74839A'); cv.cell(r,3,v).font=F(); cv.cell(r,3).alignment=Alignment(horizontal='right')
        for c in (2,3): cv.cell(r,c).border=Border(bottom=LN)
    cv['B13']='תמונת מצב'; cv['B13'].font=F(bold=True,size=14)
    stat=[('סעיפים בכתב',len(items)),('נמדדו / יש כמות',nq),('חלקיים',npart),('הוזנו ידנית',nman),('חסרה כמות',len(items)-nq)]
    for i,(k,v) in enumerate(stat):
        r=14+i; cv.cell(r,2,k).font=F(); c=cv.cell(r,3,v); c.font=F(bold=True,size=13); c.alignment=Alignment(horizontal='right')
        cv.cell(r,2).border=cv.cell(r,3).border=Border(bottom=LN)
    for r_,c_ in ((20,'הכמויות נמדדו נטו, מותקן באתר, ללא תוספת פחת, אלא אם צוין אחרת בסעיף.'),(21,'סעיפים צהובים: כמות חלקית. סעיפים אדומים: חסרה כמות. פירוט בלשונית "מה חסר למערכת".'),(22,'מקור הכמות ואופן המדידה מפורטים בלשונית "שיטות ומקורות".')):
        cv.cell(r_,2,c_).font=F(size=11,color='43536A'); cv.merge_cells(start_row=r_,start_column=2,end_row=r_,end_column=4); cv.cell(r_,2).alignment=Alignment(wrap_text=True,vertical='top'); cv.row_dimensions[r_].height=32
    sm=wb.create_sheet('סיכום פרקים',1); sm.sheet_view.rightToLeft=True
    sm.append(['פרק','שם הפרק','סעיפים','עם כמות','% כיסוי','סה"כ מתומחר'])
    for c in sm[1]: c.font=F(bold=True,color='FFFFFF'); c.fill=DK; c.alignment=Alignment(horizontal='center')
    chs=[]; cur=None
    for r in rows:
        if r['kind']=='ch': cur=dict(code=r['code'][:2],desc=r['desc'],n=0,q=0,tot=0.0); chs.append(cur)
        elif r['kind']=='item' and cur:
            cur['n']+=1; cur['q']+= r['q'] is not None
            cur['tot']+=(r['q'] or 0)*prices.get(r['code'],0)
    for i,c in enumerate(chs,2):
        sm.append([c['code'],c['desc'],c['n'],c['q'],f'=IF(C{i}=0,0,D{i}/C{i})',c['tot']])
        sm.cell(i,5).number_format='0%'; sm.cell(i,6).number_format=NF
    n=len(chs)+2; sm.cell(n,2,'סה"כ').font=F(bold=True)
    for col in (3,4,6): sm.cell(n,col,f'=SUM({"ABCDEF"[col-1]}2:{"ABCDEF"[col-1]}{n-1})').font=F(bold=True)
    sm.cell(n,6).number_format=NF
    for col,w in zip('ABCDEF',[8,40,10,10,10,16]): sm.column_dimensions[col].width=w
    me=wb.create_sheet('שיטות ומקורות'); me.sheet_view.rightToLeft=True
    me.append(['מספר','תאור','יח\'','אופן המדידה','מקור הכמות','מידת אימות הכלל'])
    for c in me[1]: c.font=F(bold=True,color='FFFFFF'); c.fill=DK
    for r in items:
        me.append([r['code'],r['desc'],r['unit'],r.get('method',''),r.get('src',''),'מאומת' if r.get('vsrc')=='v' else ('לאימות' if r.get('method') else '')])
        me.cell(me.max_row,4).alignment=Alignment(wrap_text=True,vertical='top')
        me.cell(me.max_row,2).alignment=Alignment(wrap_text=True,vertical='top')
    for col,w in zip('ABCDEF',[12,50,8,60,28,14]): me.column_dimensions[col].width=w
    me.freeze_panes='A2'
    for ws_ in (cv,sm,me):
        ws_.page_setup.orientation='landscape' if ws_ is not cv else 'portrait'; ws_.page_setup.fitToWidth=1; ws_.page_setup.fitToHeight=0; ws_.sheet_properties.pageSetUpPr=openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)
    wb.active=0
    wb.save(path)
