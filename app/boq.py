"""Builds a hierarchical BOQ (NN.00.0000 chapter / NN.SS.0000 sub / NN.SS.IIII item) from engine lines,
adds the items every project is expected to have (missing ones stay without quantity), and lists what the brain needs."""
import datetime, io, os, openpyxl, openpyxl.worksheet.properties
from openpyxl.styles import Font, PatternFill, Alignment
from .classify import TYPES

from .spec import SPEC, CHAPTERS as CH
from .brain import toks
from .phrasing import FULL,NOTES
SUB={(2,2):'תבניות וזיון',(4,2):'אלמנטים משולבים',(6,2):'מעקות ומסגרות',(7,2):'צנרת',(8,2):'תעלות וכבלים',(8,3):'לוחות',(10,2):'חיפוי קירות',(40,2):'אדמה וגינון'}
def _sub(ch,sub): return SUB.get((ch,sub),'סעיפים ראשיים' if sub==1 else 'סעיפים נוספים')
EXPECTED=[(s['ch'],s['sub'],s['desc'],s['unit'],s['plan'],'לקבלת הכמות: '+s['method'],s) for s in SPEC]
BUILT={'foundation_piles','floor_plan','elevation','electrical','tile_layout'}
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
    for l in lines: items.setdefault((l['ch'],l.get('sub',1)),[]).append(dict(trace=l.get('trace'),desc=l['desc'],unit=l['unit'],q=l['q'],st=l['st'],src=l['src'],need=l.get('need',''),method=l.get('method',''),vsrc=l.get('vsrc','')))
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
            for j,t in enumerate(NOTES.get((ch,sub),[]),1): rows.append(dict(kind='note',code=f'{ch:02d}.{sub:02d}.{j:04d}',desc=f'{"אבגדהו"[j-1]}. {t}',unit='הערה'))
            for i,it in enumerate(items[(ch,sub)],1):
                rows.append(dict(kind='item',code=f'{ch:02d}.{sub:02d}.{i*10:04d}',desc=it['desc'],full=FULL.get(it['desc'],it['desc']),unit=it['unit'],q=it['q'],src=f"{it['st']} · {it['src']}",need=it['need'],st=it['st'],method=it.get('method',''),vsrc=it.get('vsrc',''),trace=it.get('trace')))
    return rows

def needs(sheets,missing_types,unbuilt_types,assumptions):
    out=[]
    for t in missing_types:
        out.append(dict(p='high',t=f'גיליון מסוג: {TYPES[t]}',why='לא נמצא בתיק, ולכן הסעיפים התלויים בו נשארו בלי כמות',gives='ראה סעיפים עם "חסר גיליון"',how='העלה את הגיליון'))
    for t in unbuilt_types:
        out.append(dict(p='med',t=f'מנוע חישוב ל: {TYPES[t]}',why='הגיליון זוהה, אבל המנוע לסוג הזה עוד לא נבנה, או שדרוש תיוג ממך',gives='סעיפים תלויים',how='שלח דוגמה לאימון המנוע, או הזן כמויות ידנית'))
    for a in assumptions: out.append(dict(p='med',t=a['t'],why=a['why'],gives=a.get('gives','דיוק הכמויות'),how=a['how']))
    return out

GUIDE=[
('1. מספור הסעיפים',[
 'מספר סעיף = פרק.תת-פרק.פריט, למשל 10.01.0020: פרק 10 (ריצוף וחיפוי), תת-פרק 01, פריט 0020.',
 'מספרי הפרקים הם מספרי הפרקים של המפרט הכללי לעבודות בנייה ("הספר הכחול"), כך שקבלנים, מפקחים ותוכנות ניהול מדברים באותה שפה.',
 'הפריטים ממוספרים בקפיצות של 10, כדי להשאיר מקום לסעיפים שיתווספו בשינויים בלי למספר מחדש.']),
('2. כללי מדידה',[
 'כל הכמויות נמדדות נטו, לפי המידות בפועל של העבודה הגמורה. פחת, חיתוכים, חפיפות ושאריות כלולים במחיר היחידה ואינם מתווספים לכמות.',
 'ריצוף: שטח רצפה נטו בין קירות מטויחים או מחופים. המצע, הדבק, הרובה והפילוס כלולים במחיר. פנלים נמדדים בנפרד במ"א, בניכוי פתחי דלתות.',
 'טיח, חיפוי וצבע על קירות: היקף × גובה, בניכוי פתחים ששטחם מעל 0.5 מ"ר. פתחים קטנים יותר אינם מנוכים, ובתמורה החשפים שלהם אינם נמדדים בנפרד.',
 'איטום רצפות: שטח הרצפה בתוספת העלייה על הקירות. איטום קירות במקלחון נמדד בנפרד.',
 'תקרות גבס: לפי שטח ההיטל האופקי. סינרים והנמכות היקפיות במ"א. פתחי שירות ביחידות.',
 'נקודה בחשמל: הכול מהלוח ועד לאביזר הסופי, כולל צנרת, מוליכים, קופסאות, חציבה וסתימה, האביזר והחיבור. בתברואה: מהמחלק ועד לברז או לכלי הסניטרי, כולל חציבה ואביזרים.',
 'קומפלט: עבודה שלמה ומושלמת, כולל כל החומרים, האביזרים, העבודה, הבדיקות והתיאומים הנדרשים לתוצאה עובדת.',
 'אלומיניום ודלתות: ביחידות עם מידות מפורשות. המחיר כולל זיגוג, פרזול, רשת, איטום והתקנה.',
 'הריסות ופירוקים: כוללים הורדה לקומת הקרקע והעמסה למכולה. מכולות נמדדות ביחידות לפי ספירה בפועל.',
 'שעת עבודה בעבודות רג\'י נמדדת לפי יומני עבודה חתומים בידי המפקח בלבד.',
 'מחיר יסוד: מחיר אספקה של פריט שהמזמין בוחר. מחיר היחידה כולל את ההתקנה. ההפרש בין מחיר הרכישה בפועל למחיר היסוד מתווסף או מקוזז לפי חשבונית.',
 'סכום זמני: סכום שמור לעבודות בלתי צפויות, מבוצע רק לפי הוראה בכתב. היתרה מקוזזת בחשבון הסופי.']),
('3. מה כלול במחיר היחידה',[
 'חומרים, עבודה, ציוד, פיגומים והרמה, הובלה, פחת, הגנות על עבודות גמורות, ניקיון שוטף, בדיקות, אחריות, ביטוחים, ניהול, רווח ותקורה.',
 'אין סעיף "שונות": כל מה שנדרש לביצוע מושלם של הסעיף ולא נכתב בו, כלול בו.',
 'המחירים ללא מע"מ. המע"מ מחושב בשורת הריכוז לפי השיעור שבתא הכחול.',
 'הכמויות הן אומדן מדויק ככל האפשר לפי התוכניות. התשלום לפי מדידה בפועל, במחירי היחידה שבהצעה.']),
('4. איך משתמשים בקובץ',[
 'בגיליון "כתב כמויות" ממלאים מחיר יחידה בתאים הצהובים בלבד. סה"כ לסעיף, לפרק, הריכוז, המע"מ והסה"כ הכולל מחושבים אוטומטית.',
 'שורה אדומה: חסרה כמות. שורה צהובה: כמות חלקית או הנחה. פירוט בלשונית "מה חסר למערכת" ובלשונית "שורות חסרות לפי פרק".',
 'כל הנוסחאות חיות. אין לדרוס תאים מחושבים בערכים קבועים.'])]

def _tender_sheet(wb,rows,name,prices,meta,vat):
    """a clean tender-style bill: title, chapter bands, item rows with borders, yellow price cells, live totals and VAT"""
    from openpyxl.styles import Border, Side
    NV='1F3864'; thin=Side(style='thin',color='9AA5B8'); dbl=Side(style='double',color='1F3864')
    BD=Border(left=thin,right=thin,top=thin,bottom=thin); NF='#,##0.00'
    ws=wb.create_sheet('כתב כמויות',1); ws.sheet_view.rightToLeft=True; ws.sheet_view.showGridLines=False
    fnt=lambda **k:Font(name='Arial',size=k.pop('size',10),**k)
    for col,w in zip('ABCDEF',[12,70,9,11,14,17]): ws.column_dimensions[col].width=w
    ws.merge_cells('A1:F1'); ws['A1']=f'כתב כמויות · {name}'; ws['A1'].font=fnt(size=16,bold=True,color=NV); ws.row_dimensions[1].height=26
    ws.merge_cells('A2:F2'); ws['A2']=(meta.get('client') and 'עבור: '+meta['client']+'  ·  ' or '')+datetime.date.today().strftime('%d/%m/%Y')+'  ·  מחירים ללא מע"מ'; ws['A2'].font=fnt(size=10,color='595959')
    ws.merge_cells('A3:F3'); ws['A3']='ממלאים מחיר יחידה בתאים הצהובים בלבד. הסכומים מחושבים אוטומטית. כללי המדידה בלשונית "הנחיות".'; ws['A3'].font=fnt(size=9,color='C00000')
    hdr=['סעיף','תיאור',"יח'",'כמות','מחיר יחידה','סה"כ']
    for i,h in enumerate(hdr,1):
        c=ws.cell(5,i,h); c.font=fnt(bold=True,color='FFFFFF'); c.fill=PatternFill('solid',fgColor=NV); c.alignment=Alignment(horizontal='center',vertical='center',wrap_text=True); c.border=BD
    ws.row_dimensions[5].height=22
    r=6; chap_tot=[]; cur=None
    def close():
        nonlocal r,cur
        if cur and cur['items']:
            ws.cell(r,2,f'סה"כ {cur["name"]}')
            ws.cell(r,6,'=SUM('+','.join(f'F{a}:F{b}' for a,b in cur['spans'])+')')
            for col in range(1,7):
                c=ws.cell(r,col); c.font=fnt(bold=True); c.fill=PatternFill('solid',fgColor='EDEDED'); c.border=Border(left=thin,right=thin,top=dbl,bottom=dbl)
            ws.cell(r,6).number_format=NF; chap_tot.append(r); r+=2
        cur=None
    for x in rows:
        k=x['kind']
        if k=='ch':
            if x['desc']==name: continue
            close(); cur=dict(name=x['desc'],items=0,spans=[],start=None)
            ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=6)
            c=ws.cell(r,1,f'פרק {x["code"][:2]} — {x["desc"]}'); c.font=fnt(size=11,bold=True,color='FFFFFF'); c.fill=PatternFill('solid',fgColor=NV); c.alignment=Alignment(horizontal='right',vertical='center'); ws.row_dimensions[r].height=22; r+=1
        elif k=='sub' and cur is not None:
            ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=6)
            c=ws.cell(r,1,f'{x["code"][:5]}  {x["desc"]}'); c.font=fnt(size=10,bold=True,color=NV); c.fill=PatternFill('solid',fgColor='D9E1F2'); c.alignment=Alignment(horizontal='right'); r+=1
            cur['start']=None
        elif k=='note' and cur is not None:
            ws.merge_cells(start_row=r,start_column=2,end_row=r,end_column=6)
            c=ws.cell(r,2,x['desc']); c.font=fnt(size=9,italic=True,color='595959'); c.alignment=Alignment(wrap_text=True,vertical='top',horizontal='right'); ws.row_dimensions[r].height=max(15,13*(1+len(x['desc'])//95)); r+=1
        elif k=='item' and cur is not None:
            dsc=x.get('full') or x['desc']
            ws.cell(r,1,x['code']); ws.cell(r,2,dsc); ws.cell(r,3,x['unit']); ws.cell(r,4,x['q']); ws.cell(r,5,prices.get(x['code']) or None)
            ws.cell(r,6,f'=IF(OR(D{r}="",E{r}=""),0,D{r}*E{r})')
            for col in range(1,7):
                c=ws.cell(r,col); c.border=BD; c.font=fnt(color='0000FF' if col==4 else '000000')
                c.alignment=Alignment(horizontal='center' if col in(1,3) else 'right',vertical='top',wrap_text=(col==2))
            ws.cell(r,4).number_format=NF; ws.cell(r,5).number_format=NF; ws.cell(r,6).number_format=NF
            ws.cell(r,5).fill=PatternFill('solid',fgColor='FFF2CC')
            if x['q'] is None: ws.cell(r,4).fill=PatternFill('solid',fgColor='FDE2E2')
            elif x.get('st')=='חלקי': ws.cell(r,4).fill=PatternFill('solid',fgColor='FFF4D1')
            ws.row_dimensions[r].height=max(15,13.5*(1+len(dsc)//80))
            if cur['spans'] and cur['spans'][-1][1]==r-1: cur['spans'][-1]=(cur['spans'][-1][0],r)
            else: cur['spans'].append((r,r))
            cur['items']+=1; r+=1
    close()
    r+=1; ws.cell(r,2,'ריכוז פרקים').font=fnt(size=12,bold=True,color=NV); r+=1
    first=r
    for tr in chap_tot:
        ws.cell(r,2,f'=B{tr}'); ws.cell(r,6,f'=F{tr}'); ws.cell(r,6).number_format=NF
        for col in (2,6): ws.cell(r,col).border=BD; ws.cell(r,col).font=fnt()
        r+=1
    ws.cell(r,2,'סה"כ לפני מע"מ'); ws.cell(r,6,f'=SUM(F{first}:F{r-1})'); st=r; r+=1
    ws.cell(r,2,'שיעור מע"מ'); ws.cell(r,6,vat); ws.cell(r,6).number_format='0%'; ws.cell(r,6).font=fnt(color='0000FF',bold=True); vr=r; r+=1
    ws.cell(r,2,'מע"מ'); ws.cell(r,6,f'=F{st}*F{vr}'); mr=r; r+=1
    ws.cell(r,2,'סה"כ כולל מע"מ'); ws.cell(r,6,f'=F{st}+F{mr}')
    for rr in (st,mr,r):
        ws.cell(rr,6).number_format=NF
        for col in (2,6): ws.cell(rr,col).font=fnt(bold=True,size=11); ws.cell(rr,col).fill=PatternFill('solid',fgColor='EDEDED'); ws.cell(rr,col).border=BD
    ws.freeze_panes='A6'; ws.print_title_rows='5:5'; ws.page_setup.orientation='portrait'; ws.page_setup.paperSize=9
    ws.page_setup.fitToWidth=1; ws.page_setup.fitToHeight=0; ws.sheet_properties.pageSetUpPr=openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)
    ws.print_options.horizontalCentered=True; ws.oddFooter.center.text=f'{name}  |  &P / &N'
    return ws

def _guidelines(wb):
    ws=wb.create_sheet('הנחיות',2); ws.sheet_view.rightToLeft=True; ws.sheet_view.showGridLines=False
    ws.column_dimensions['A'].width=4; ws.column_dimensions['B'].width=120
    f=lambda **k:Font(name='Arial',size=k.pop('size',10),**k)
    ws['A1']='הנחיות לקריאת כתב הכמויות ולמילויו'; ws['A1'].font=f(size=16,bold=True,color='1F3864'); r=3
    for h,lines in GUIDE:
        ws.cell(r,1,h).font=f(size=11,bold=True,color='1F3864'); r+=1
        for t in lines:
            c=ws.cell(r,2,t); c.font=f(); c.alignment=Alignment(wrap_text=True,vertical='top',horizontal='right'); ws.row_dimensions[r].height=max(15,14*(1+len(t)//125)); r+=1
        r+=1
    ws.page_setup.orientation='portrait'; ws.page_setup.fitToWidth=1; ws.page_setup.fitToHeight=0; ws.sheet_properties.pageSetUpPr=openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)

def to_xlsx(rows,name,path,needs_list=(),prices=None,meta=None,hide=(),ctx=None):
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
    SUBF=PatternFill('solid',fgColor='E2D9F0'); CHT=PatternFill('solid',fgColor='A9A6DE')
    state=dict(sub=None,ch=None)   # sub: dict(name,rows=[]) ; ch: dict(name,subs=[cells])
    def tot_rows(kind,name,cells):
        """three rows as in the reference report: total, discount %, total after discount; returns cell of the after-discount total"""
        nonlocal r2
        fill=SUBF if kind=='sub' else CHT; lab='תת פרק' if kind=='sub' else 'פרק'
        t.cell(r2,2,f'סה"כ {lab} {name}'); t.cell(r2,6,'='+('+'.join(f'F{x}' for x in cells) if cells else '0')); tr=r2; r2+=1
        t.cell(r2,2,f'אחוז הנחה {lab} {name}'); t.cell(r2,6,0); t.cell(r2,6).number_format='0.0%'; t.cell(r2,6).fill=PatternFill('solid',fgColor='FFF4D1'); dr=r2; r2+=1
        t.cell(r2,2,f'סה"כ לאחר הנחה {lab} {name}'); t.cell(r2,6,f'=F{tr}*(1-F{dr})'); t.cell(r2,6).number_format=NF; ar=r2; r2+=1
        for rr in (tr,dr,ar):
            for c in t[rr][:7]:
                c.font=F(bold=True); 
                if c.column!=6 or rr!=dr: c.fill=fill
        t.cell(tr,6).number_format=NF
        return ar
    def close_sub():
        if state['sub'] and state['ch'] is not None:
            state['ch']['subs'].append(tot_rows('sub',state['sub']['name'],state['sub']['rows']))
        state['sub']=None
    def close_ch():
        close_sub()
        if state['ch'] is not None and state['ch']['subs']:
            state['all'].append(tot_rows('ch',state['ch']['name'],state['ch']['subs']))
        state['ch']=None
    state['all']=[]
    for r in rows:
        k=r['kind']; ra=a.max_row+1
        if k in('ch','sub','note'):
            if k=='ch' and r['desc']!=name: close_ch(); state['ch']=dict(name=r['desc'],subs=[])
            if k=='sub': close_sub(); state['sub']=dict(name=r['desc'],rows=[])
            a.append([r['code'],r['desc']]+([r['unit']] if k=='note' else [])); t.cell(r2,1,r['code']); t.cell(r2,2,r['desc'])
            if k=='note': t.cell(r2,3,'הערה')
            for ws,rr in ((a,ra),(t,r2)):
                for c in ws[rr]: c.font=F(bold=(k!='note'))
                if k=='ch':
                    for c in ws[rr]: c.fill=CHF
                if k=='note': ws.cell(rr,2).alignment=Alignment(wrap_text=True,vertical='top')
        else:
            dsc=r.get('full') or r['desc']
            a.append([r['code'],dsc,' '+r['unit'],r['q'],0,f'=E{ra}*D{ra}',0,f'=G{ra}*D{ra}',r['src']+(f" · חסר: {r['need']}" if r.get('need') else '')])
            a.cell(ra,5).value=prices.get(r['code'],0)
            t.cell(r2,1,r['code']); t.cell(r2,2,dsc); t.cell(r2,3,' '+r['unit']); t.cell(r2,4,r['q']); t.cell(r2,5,prices.get(r['code'],0)); t.cell(r2,6,f'=E{r2}*D{r2}')
            if state['sub']: state['sub']['rows'].append(r2)
            for col in (5,6,7,8): a.cell(ra,col).number_format=NF
            for col in (5,6): t.cell(r2,col).number_format=NF
            for ws,rr in ((a,ra),(t,r2)): ws.cell(rr,2).alignment=Alignment(wrap_text=True,vertical='top')
            fill=MISS if r['q'] is None else (PART if r.get('st')=='חלקי' else None)
            if fill: a.cell(ra,4).fill=fill; t.cell(r2,4).fill=fill
        r2+=1
    close_ch()
    t.cell(r2,2,'סה"כ כללי לאחר הנחות').font=F(bold=True); t.cell(r2,6,'='+('+'.join(f'F{x}' for x in state['all']) if state['all'] else '0')).font=F(bold=True); t.cell(r2,6).number_format=NF
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
    try:
        _tender_sheet(wb,rows,name,prices,meta,(meta.get('vat') or 0.18)); _guidelines(wb)
    except Exception as _e: print('tender sheet failed',_e)
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
    miss=[r for r in items if r.get('q') is None or r.get('st')=='חלקי']
    if miss:
        mm=wb.create_sheet('שורות חסרות לפי פרק'); mm.sheet_view.rightToLeft=True
        mm.append(['פרק','מספר','תאור','יח\'','מצב','למה חסר / מה חסר'])
        for c in mm[1]: c.font=F(bold=True,color='FFFFFF'); c.fill=DK
        chname={}
        for r in rows:
            if r['kind']=='ch': chname[r['code'][:2]]=r['desc']
        for r in miss:
            mm.append([chname.get(r['code'][:2],''),r['code'],r.get('full') or r['desc'],r['unit'],'חסרה כמות' if r.get('q') is None else 'כמות חלקית',r.get('need','')])
            mm.cell(mm.max_row,5).fill=MISS if r.get('q') is None else PART
            for ci in (3,6): mm.cell(mm.max_row,ci).alignment=Alignment(wrap_text=True,vertical='top')
        for col,w in zip('ABCDEF',[26,12,60,8,14,70]): mm.column_dimensions[col].width=w
        mm.freeze_panes='A2'
    tr=[r for r in items if r.get('trace')]
    if tr:
        tc=wb.create_sheet('דפי חישוב'); tc.sheet_view.rightToLeft=True
        for r in tr:
            t_=r['trace']; tc.append([r['code'],r.get('full') or r['desc'],r['unit']]); 
            for c in tc[tc.max_row]: c.font=F(bold=True); c.fill=CHF
            tc.append(['','שיטה: '+t_.get('formula','')]); 
            tc.append(['','אלמנט','מידות (מ\')','כמות','מקור','הערה'])
            for c in tc[tc.max_row]: c.font=F(bold=True,color='FFFFFF'); c.fill=DK
            for x in t_.get('rows',[]): tc.append(['',x['el'],x.get('dims',''),x['val'],x.get('src',''),x.get('note','')])
            tc.append(['','סה"כ בסעיף','',r['q'],'',''])
            for c in tc[tc.max_row]: c.font=F(bold=True)
            for c_ in t_.get('checks',[]): tc.append(['',('✓ ' if c_['ok'] else '✗ ')+c_['t']])
            if ctx:
                try:
                    from . import report as RP
                    from openpyxl.drawing.image import Image as XI
                    imgs,_n=RP.item_images(ctx['pr'],ctx['files_dir'],t_,760)
                    for cap,png in imgs[:2]:
                        tc.append(['','תמונה: '+cap]); im=XI(io.BytesIO(png)); sc=min(1.0,720/im.width); im.width*=sc; im.height*=sc
                        tc.add_image(im,f'B{tc.max_row+1}'); tc.append([]); 
                        for _ in range(int(im.height/20)+1): tc.append([])
                except Exception: pass
            tc.append([])
        for col,w in zip('ABCDEF',[12,46,18,10,30,40]): tc.column_dimensions[col].width=w
    if ctx:
        from . import report as RP
        from .classify import TYPES
        pr_=ctx['pr']; used={}; cur=''; chs=[]; ccur=None
        for rw in pr_.get('boq') or []:
            if rw['kind']=='ch' and rw['desc']!=pr_['name']: cur=rw['desc']; ccur=(cur,[]); chs.append(ccur)
            elif rw['kind']=='item':
                if ccur: ccur[1].append(rw)
                for x in (rw.get('trace') or {}).get('rows',[]):
                    for lc in x.get('locs') or []: used.setdefault(lc['sid'],set()).add(cur)
        pl=wb.create_sheet('תוכניות שהסתמכנו'); pl.sheet_view.rightToLeft=True
        pl.append(['#','תצוגה','סוג שזוהה','קומה','פרקים שנשענים על הגיליון']); 
        for c in pl[1]: c.font=F(bold=True,color='FFFFFF'); c.fill=DK
        from openpyxl.drawing.image import Image as XI
        for i,s in enumerate(pr_['sheets']):
            pl.append([i+1,'',TYPES.get(s.get('type'),'לא זוהה'),s.get('floor') or '',', '.join(sorted(used.get(s['sid'],[]))) or 'לא שימש לחישוב'])
            pl.row_dimensions[pl.max_row].height=70
            try:
                p=os.path.join(ctx['files_dir'],s['sid']+'.pdf'); import base64
                im=XI(io.BytesIO(base64.b64decode(RP.thumb(p,150)))); pl.add_image(im,f'B{pl.max_row}')
            except Exception: pass
            pl.cell(pl.max_row,5).alignment=Alignment(wrap_text=True,vertical='top')
        for col,w in zip('ABCDE',[5,24,26,10,70]): pl.column_dimensions[col].width=w
        wc=wb.create_sheet('שימו לב לפי פרק'); wc.sheet_view.rightToLeft=True
        wc.append(['פרק','מה כדאי לשים לב / מה אולי לא חושב']);
        for c in wc[1]: c.font=F(bold=True,color='FFFFFF'); c.fill=DK
        for nm,its in chs:
            for x in RP.cautions(nm,its):
                wc.append([nm,x]); wc.cell(wc.max_row,2).alignment=Alignment(wrap_text=True,vertical='top')
        wc.column_dimensions['A'].width=30; wc.column_dimensions['B'].width=110
    for ws_ in (cv,sm,me):
        ws_.page_setup.orientation='landscape' if ws_ is not cv else 'portrait'; ws_.page_setup.fitToWidth=1; ws_.page_setup.fitToHeight=0; ws_.sheet_properties.pageSetUpPr=openpyxl.worksheet.properties.PageSetupProperties(fitToPage=True)
    H={'price':('E','G'),'total':('F','H'),'src':('I',),'rum':('G','H')}
    for k in hide or ():
        for col in H.get(k,()): a.column_dimensions[col].hidden=True
        for col,tc in (('E','E'),('F','F'),('I','G')):
            pass
    if 'price' in (hide or ()): t.column_dimensions['E'].hidden=True
    if 'total' in (hide or ()): t.column_dimensions['F'].hidden=True
    if 'src' in (hide or ()): t.column_dimensions['G'].hidden=True
    wb.active=0
    wb.save(path)
