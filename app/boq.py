"""Builds a hierarchical BOQ (NN.00.0000 chapter / NN.SS.0000 sub / NN.SS.IIII item) from engine lines,
adds the items every project is expected to have (missing ones stay without quantity), and lists what the brain needs."""
import datetime, openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from .classify import TYPES

CH={1:'עבודות עפר',2:'עבודות בטון יצוק באתר',4:'עבודות בניה',5:'עבודות איטום',6:'עבודות נגרות ומסגרות',7:'מערכות תברואה',8:'מתקני חשמל',9:'עבודות טיח',10:'עבודות ריצוף וחיפוי',11:'עבודות צביעה',13:'עבודות גבס ותקרות (מספר פרק להשלמה)',23:'כלונסאות',30:'ריהוט וציוד מורכב בבניין',40:'פיתוח נופי וגדרות'}
SUB={(1,1):'חפירה ומילוי',(2,1):'בטון יצוק באתר',(4,1):'קירות',(5,1):'איטום',(6,1):'דלתות וחלונות',(7,1):'קבועות תברואה',(7,2):'צנרת מים וביוב',(8,1):'גופי תאורה ונקודות',(9,1):'טיח',(10,1):'ריצוף',(11,1):'צבע',(13,1):'תקרות',(23,1):'כלונסאות קדוחים',(30,1):'מקבעים',(40,1):'גדרות, שער ופיתוח'}
# (chapter, sub, description, unit, needed sheet type, what is needed, engine key that covers it)
EXPECTED=[
 (1,1,'חפירה לראשי כלונסאות ולקורות יסוד, כולל פינוי עודפי חפירה','מ"ק','section','מפלסים ומידות ראשי הכלונסאות',None),
 (2,1,'בטון ראשי כלונסאות ויסודות, לפי תוכנית יסודות','מ"ק','foundation_piles','מידות וגבהים מהפרטים',None),
 (2,1,'בטון בקירות ועמודים','מ"ק','structure_plan','מיפוי שכבות בגיליונות הקונסטרוקציה',None),
 (2,1,'תקרות ורצפות בטון מזוין, לפי תוכניות תקרה','מ"ר','structure_plan','מיפוי שכבות בגיליונות התקרה',None),
 (2,1,'מוטות פלדה מצולעים ורשתות מרותכות לזיון הבטון','טון','structure_plan','OCR של טבלאות הזיון',None),
 (4,1,'גובה קומה וגובה תקרה (נתון לחישוב שטחי קירות)',"קומפ'",'section','מפלסים בחתכים (OCR) או הזנה ידנית',None),
 (5,1,'איטום רצפת חדרים רטובים ומרפסות. המדידה נטו בין מחיצות, לפי שטח הריצוף','מ"ר','floor_plan','זיהוי חדרים רטובים בתוכנית אדריכלות',None),
 (6,1,'דלתות וחלונות לפי פרטי דלתות וחלונות',"יח'",'openings_details','ספירה לפי תגיות',None),
 (7,1,'כלים סניטריים',"יח'",'plumbing','תוכנית אינסטלציה או שכבת כלים סניטריים',None),
 (7,2,'קווי מים וביוב','מטר','plumbing','תוכנית אינסטלציה',None),
 (8,1,'נקודות חשמל לפי סוג (שקעים, מפסקים, גופי תאורה)',"נק'",'electrical','התאמת סמלים למקרא (תיוג דוגמאות)',None),
 (9,1,'טיח פנים וחוץ, לפי שטחי קירות בניכוי פתחים','מ"ר','floor_plan','היקף חדר כפול גובה פחות פתחים',None),
 (11,1,'צבע פנים, לפי שטחי קירות ותקרות','מ"ר','floor_plan','כמו בטיח',None),
 (13,1,'תקרות גבס ומונמכות','מ"ר','floor_plan','סימוני תקרה',None),
 (23,1,'אורך כלונסאות כולל','מטר','foundation_piles','טבלת מפלסים (OCR) או הזנת אורך',None),
 (30,1,'ריהוט קבוע ונגרות פנים',"יח'",'floor_plan','שכבת ריהוט או רשימת פריטים',None),
 (40,1,'גדרות, שער וריצוף חוץ לפי תוכנית פיתוח','מטר','site','תוכנית פיתוח',None),
]
BUILT={'foundation_piles','floor_plan','elevation','electrical'}   # types that have an engine today

def build(name,lines,present_types):
    items={}   # (ch,sub) -> list of dict
    for l in lines: items.setdefault((l['ch'],l.get('sub',1)),[]).append(dict(desc=l['desc'],unit=l['unit'],q=l['q'],st=l['st'],src=l['src'],need=l.get('need','')))
    for ch,sub,desc,unit,typ,need,_ in EXPECTED:
        if typ in present_types: why=f'יש גיליון מסוג "{TYPES[typ]}", המנוע לסוג זה טרם נבנה' if typ not in BUILT else need
        else: why=f'חסר גיליון מסוג "{TYPES[typ]}". {need}'
        items.setdefault((ch,sub),[]).append(dict(desc=desc,unit=unit,q=None,st='דורש השלמה',src=TYPES[typ],need=why))
    rows=[dict(kind='ch',code='00.00.0000',desc=name)]
    for ch in sorted({k[0] for k in items}):
        rows.append(dict(kind='ch',code=f'{ch:02d}.00.0000',desc=CH.get(ch,f'פרק {ch}')))
        for sub in sorted(k[1] for k in items if k[0]==ch):
            rows.append(dict(kind='sub',code=f'{ch:02d}.{sub:02d}.0000',desc=SUB.get((ch,sub),CH.get(ch,''))))
            for i,it in enumerate(items[(ch,sub)],1):
                rows.append(dict(kind='item',code=f'{ch:02d}.{sub:02d}.{i*10:04d}',desc=it['desc'],unit=it['unit'],q=it['q'],src=f"{it['st']} · {it['src']}",need=it['need'],st=it['st']))
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
    a.freeze_panes='A2'; t.freeze_panes='A16'
    m=wb.create_sheet('מה חסר למערכת'); m.sheet_view.rightToLeft=True; m.append(['דחיפות','מה חסר','למה','מה זה משחרר','מה לעשות'])
    P={'high':'דחוף','med':'חשוב','low':'כשיהיה זמן'}
    for n in needs_list: m.append([P[n['p']],n['t'],n['why'],n['gives'],n['how']])
    for col,w in zip('ABCDE',[12,45,60,28,36]): m.column_dimensions[col].width=w
    wb.save(path)
