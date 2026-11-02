"""Premium Excel quote: cover/summary sheet + grouped BOQ with live formulas."""
import datetime, openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.chart import DoughnutChart, Reference
from openpyxl.worksheet.properties import PageSetupProperties
from .quote_pdf import summarize

NAVY='041A3F'; BLUE='1F6FD1'; SKY='5CB0FF'; LIGHT='E8F0FC'; ZEB='F7FAFF'
def to_xlsx(pr,rows,prices,path,company=None,opts=None):
    company=company or {}; opts=opts or {}
    chs=summarize(rows,prices); vat_p=float(opts.get('vat',18)); dp=float(opts.get('discount',0) or 0)
    F=lambda **k:Font(name='Arial',size=k.pop('size',10),**k); fill=lambda c:PatternFill('solid',fgColor=c)
    thin=Side(style='thin',color='DCE4F0'); bt=Border(bottom=thin)
    NF='#,##0.00'; NI='#,##0'
    wb=openpyxl.Workbook(); S=wb.active; S.title='סיכום'; D=wb.create_sheet('כתב כמויות מתומחר')
    for ws in (S,D): ws.sheet_view.rightToLeft=True; ws.sheet_view.showGridLines=False
    # ---- detail sheet ----
    for col,w in zip('ABCDEFG',[12,70,9,11,13,15,34]): D.column_dimensions[col].width=w
    D.merge_cells('A1:G1'); D['A1']=f"הצעת מחיר · {pr['name']}"; D['A1'].font=F(bold=True,size=16,color='FFFFFF'); D['A1'].fill=fill(NAVY); D['A1'].alignment=Alignment(vertical='center',indent=1); D.row_dimensions[1].height=34
    hdr=['סעיף','תיאור','יח\'','כמות','מחיר יח\'','סה"כ','הערות']
    for i,h in enumerate(hdr,1):
        c=D.cell(3,i,h); c.font=F(bold=True,color='FFFFFF'); c.fill=fill(BLUE); c.alignment=Alignment(horizontal='center',vertical='center')
    D.row_dimensions[3].height=22; D.freeze_panes='A4'
    r=4; ch_cells=[]
    for c in chs:
        D.merge_cells(start_row=r,start_column=1,end_row=r,end_column=5); D.cell(r,1,f"{c['code']} · {c['name']}"); chr_=r
        for col in range(1,8): D.cell(r,col).fill=fill(NAVY); D.cell(r,col).font=F(bold=True,size=11,color='FFFFFF')
        r+=1; subs=[]
        for s in c['subs']:
            if not s['items']: continue
            D.merge_cells(start_row=r,start_column=1,end_row=r,end_column=7); D.cell(r,1,s['name']); 
            for col in range(1,8): D.cell(r,col).fill=fill(LIGHT); D.cell(r,col).font=F(bold=True,color=NAVY)
            D.row_dimensions[r].height=18; r+=1; first=r
            for k,it in enumerate(s['items']):
                D.cell(r,1,it['code'][3:]).font=F(color='7A8AA6',size=9)
                D.cell(r,2,it.get('full') or it['desc']).alignment=Alignment(wrap_text=True,vertical='top')
                D.cell(r,3,it['unit']).alignment=Alignment(horizontal='center')
                q=D.cell(r,4,it['q']); q.number_format=NF
                p=D.cell(r,5,it['price']); p.number_format=NF; p.fill=fill('FFF8E1')
                t=D.cell(r,6,f'=IF(AND(ISNUMBER(D{r}),ISNUMBER(E{r})),D{r}*E{r},0)'); t.number_format=NI; t.font=F(bold=True)
                if it['q'] is None: D.cell(r,7,'חסרה כמות — '+(it.get('need') or '')); D.cell(r,4).fill=fill('FDE2E2')
                elif it.get('st')=='חלקי': D.cell(r,4).fill=fill('FFF4D1')
                for col in range(1,8):
                    D.cell(r,col).border=bt
                    if col in(2,3,4,5,7): D.cell(r,col).font=F(size=9.5 if col==2 else 10)
                    if k%2: 
                        if D.cell(r,col).fill.fgColor.rgb in('00000000',None): D.cell(r,col).fill=fill(ZEB)
                r+=1
            D.cell(r,2,f'סה"כ {s["name"]}'); D.cell(r,6,f'=SUM(F{first}:F{r-1})'); D.cell(r,6).number_format=NI
            for col in range(1,8): D.cell(r,col).font=F(bold=True,color=NAVY); D.cell(r,col).border=Border(top=Side(style='thin',color=BLUE))
            subs.append(r); r+=2
        D.cell(chr_,6,'='+('+'.join(f'F{x}' for x in subs) if subs else '0')); D.cell(chr_,6).number_format=NI
        ch_cells.append((c['code'],c['name'],chr_))
    D.page_setup.orientation='portrait'; D.page_setup.fitToWidth=1; D.page_setup.fitToHeight=0; D.sheet_properties.pageSetUpPr=PageSetupProperties(fitToPage=True)
    D.print_title_rows='3:3'
    # ---- summary sheet ----
    for col,w in zip('ABCDEF',[3,12,44,18,14,3]): S.column_dimensions[col].width=w
    for rr in range(1,60):
        for cc in range(1,7): S.cell(rr,cc).fill=fill('FFFFFF')
    for rr in range(1,9):
        for cc in range(1,7): S.cell(rr,cc).fill=fill(NAVY)
    S['B2']=company.get('name','שם החברה'); S['B2'].font=F(bold=True,size=12,color=SKY)
    S['B4']='הצעת מחיר'; S['B4'].font=F(bold=True,size=26,color='FFFFFF'); S.row_dimensions[4].height=38
    S['B6']=pr['name']; S['B6'].font=F(size=13,color='FFFFFF')
    today=datetime.date.today()
    info=[('לכבוד',pr.get('client') or '—'),('תאריך',today.strftime('%d/%m/%Y')),('בתוקף עד',(today+datetime.timedelta(days=opts.get('valid_days',30))).strftime('%d/%m/%Y')),('מספר הצעה',opts.get('number',f'Q-{today:%y%m}-{pr["id"][:4].upper()}'))]
    for i,(k,v) in enumerate(info):
        S.cell(10+i,2,k).font=F(color='7A8AA6'); S.cell(10+i,3,v).font=F(bold=True,size=11,color=NAVY)
    S.cell(15,2,'סיכום לפי פרקים').font=F(bold=True,size=13,color=NAVY)
    for i,h in enumerate(['קוד','פרק','סכום ₪','אחוז']): 
        c=S.cell(16,2+i,h); c.font=F(bold=True,color='FFFFFF'); c.fill=fill(BLUE); c.alignment=Alignment(horizontal='center')
    rr=17; nz=[x for x in ch_cells]
    first=rr
    for code,name,cr in nz:
        S.cell(rr,2,code).font=F(color='7A8AA6'); S.cell(rr,3,name)
        S.cell(rr,4,f"='כתב כמויות מתומחר'!F{cr}").number_format=NI
        for cc in range(2,6): S.cell(rr,cc).border=bt
        rr+=1
    last=rr-1
    for x in range(first,last+1): S.cell(x,5,f'=IF($D${rr}=0,0,D{x}/$D${rr})').number_format='0.0%'
    S.cell(rr,3,'סה"כ כתב כמויות'); S.cell(rr,4,f'=SUM(D{first}:D{last})')
    S.cell(rr+1,3,'הנחה %'); S.cell(rr+1,4,dp/100).number_format='0.0%'; S.cell(rr+1,4).fill=fill('FFF8E1')
    S.cell(rr+2,3,'לאחר הנחה'); S.cell(rr+2,4,f'=D{rr}*(1-D{rr+1})')
    S.cell(rr+3,3,f'מע"מ'); S.cell(rr+3,5,vat_p/100).number_format='0%'; S.cell(rr+3,4,f'=D{rr+2}*E{rr+3}')
    S.cell(rr+4,3,'סה"כ לתשלום'); S.cell(rr+4,4,f'=D{rr+2}+D{rr+3}')
    for x in range(rr,rr+5):
        S.cell(x,4).number_format=NI if x!=rr+1 else '0.0%'
        for cc in range(2,6): S.cell(x,cc).font=F(bold=True,color=NAVY)
    for cc in range(2,6): S.cell(rr+4,cc).fill=fill(NAVY); S.cell(rr+4,cc).font=F(bold=True,size=12,color='FFFFFF')
    ch=DoughnutChart(); ch.holeSize=60; ch.title=None
    top=[(i,d) for i,d in enumerate(nz)]
    ch.add_data(Reference(S,min_col=4,min_row=first,max_row=last)); ch.set_categories(Reference(S,min_col=3,min_row=first,max_row=last))
    ch.width=11; ch.height=9; ch.legend=None; S.add_chart(ch,'H15')
    S.page_setup.orientation='portrait'; S.page_setup.fitToWidth=1; S.page_setup.fitToHeight=1; S.sheet_properties.pageSetUpPr=PageSetupProperties(fitToPage=True)
    wb.save(path)
