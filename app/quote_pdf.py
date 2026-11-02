"""Premium quote (הצעת מחיר) PDF: HTML -> PDF via Playwright Chromium. No client data is embedded here."""
import datetime, html, math

NAVY='#041A3F'; BLUE='#1F6FD1'; SKY='#5CB0FF'; ORG='#D9622B'

def _n(x,d=0):
    return f'{x:,.{d}f}'
def _e(s): return html.escape(str(s if s is not None else ''))

def summarize(rows,prices):
    """chapters list: dict(code,name,total,n,subs=[dict(name,items,notes,total)])"""
    chs=[]; ch=None; sub=None
    for r in rows:
        k=r['kind']
        if k=='ch':
            ch=dict(code=r['code'][:2],name=r['desc'],subs=[],total=0.0,n=0); chs.append(ch); sub=None
        elif k=='sub' and ch is not None:
            sub=dict(code=r['code'],name=r['desc'],items=[],notes=[],total=0.0); ch['subs'].append(sub)
        elif k=='note' and sub is not None: sub['notes'].append(r['desc'])
        elif k=='item' and sub is not None:
            p=prices.get(r['code']); q=r.get('q'); t=(p or 0)*(q or 0)
            sub['items'].append(dict(r,price=p,total=t)); sub['total']+=t; ch['total']+=t; ch['n']+=1
    return [c for c in chs if c['n']]

def build_html(pr,rows,prices,company=None,opts=None,parts=False):
    company=company or {}; opts=opts or {}
    chs=summarize(rows,prices)
    sub_total=sum(c['total'] for c in chs)
    dp=float(opts.get('discount',0) or 0); disc_amt=sub_total*dp/100
    net=sub_total-disc_amt; vat_p=float(opts.get('vat',18)); vat=net*vat_p/100; gross=net+vat
    today=datetime.date.today(); valid=opts.get('valid_days',30)
    qno=opts.get('number',f'Q-{today:%y%m}-{pr["id"][:4].upper()}')
    cname=company.get('name','שם החברה שלך'); logo=company.get('logo')
    logo_html=f'<img src="{logo}" style="max-height:64px;max-width:200px">' if logo else f'<div class="lg">{_e(cname[:1])}</div>'
    top=sorted([c for c in chs if c['total']>0],key=lambda c:-c['total']); main=top[:6]; rest=sum(c['total'] for c in top[6:])
    cols=[NAVY,BLUE,SKY,ORG,'#7A8FB5','#B9C6DD','#DDE4F0']
    segs=[(c['name'],c['total']) for c in main]+([('אחר',rest)] if rest>0 else [])
    R=70; C=2*math.pi*R; off=0; arcs=''
    for i,(n,v) in enumerate(segs):
        f=v/sub_total if sub_total else 0
        arcs+=f'<circle r="{R}" cx="90" cy="90" fill="none" stroke="{cols[i]}" stroke-width="26" stroke-dasharray="{f*C:.2f} {C:.2f}" stroke-dashoffset="{-off*C:.2f}" transform="rotate(-90 90 90)"/>'
        off+=f
    legend=''.join(f'<div class="lgi"><i style="background:{cols[i]}"></i><span>{_e(n)}</span><b dir="ltr">{(v/sub_total*100 if sub_total else 0):.1f}%</b></div>' for i,(n,v) in enumerate(segs))
    mx=max([c['total'] for c in chs] or [1]) or 1
    ctab=''.join(f'<tr><td class="cd">{_e(c["code"])}</td><td>{_e(c["name"])}</td><td class="bar"><div><span style="width:{c["total"]/mx*100:.1f}%"></span></div></td><td class="num" dir="ltr">{_n(c["total"])}</td><td class="num sh" dir="ltr">{(c["total"]/sub_total*100 if sub_total else 0):.1f}%</td></tr>' for c in top[:10])+(f'<tr><td></td><td>עוד {len(top)-10} פרקים</td><td></td><td class="num" dir="ltr">{_n(sum(c["total"] for c in top[10:]))}</td><td></td></tr>' if len(top)>10 else '')
    det=''
    for c in chs:
        det+=f'<div class="ch-h"><span>{_e(c["code"])}</span><h2>{_e(c["name"])}</h2><b dir="ltr">₪ {_n(c["total"])}</b></div>'
        for s in c['subs']:
            if not s['items']: continue
            det+=f'<table class="bq"><thead><tr><th colspan="6" class="sb">{_e(s["name"])}</th></tr><tr class="th"><th style="width:70px">סעיף</th><th>תיאור</th><th style="width:44px">יח\'</th><th style="width:60px">כמות</th><th style="width:70px">מחיר יח\'</th><th style="width:84px">סה"כ</th></tr></thead><tbody>'
            for it in s['items']:
                q='' if it['q'] is None else _n(it['q'],2 if it['q']!=int(it['q']) else 0)
                p='—' if not it['price'] else _n(it['price'],2)
                tt='—' if not it['total'] else _n(it['total'])
                det+=f'<tr><td class="cd" dir="ltr">{_e(it["code"][3:])}</td><td>{_e(it.get("full") or it["desc"])}</td><td class="c">{_e(it["unit"])}</td><td class="num" dir="ltr">{q}</td><td class="num" dir="ltr">{p}</td><td class="num b" dir="ltr">{tt}</td></tr>'
            det+=f'<tr class="stt"><td colspan="5">סה"כ {_e(s["name"])}</td><td class="num" dir="ltr">{_n(s["total"])}</td></tr></tbody></table>'
    terms=opts.get('terms') or [
        'המחירים אינם כוללים מע"מ אלא אם צוין אחרת, ובתוקף ל-%d יום מתאריך ההצעה.'%valid,
        'הכמויות נמדדו מתוכניות שנמסרו; כמויות סופיות יימדדו בפועל ויחויבו לפי מדידה.',
        'סעיפים ללא מחיר כלולים בכתב הכמויות לצורך שלמות בלבד ואינם חלק מהסכום.',
        'תנאי תשלום: שוטף + 30 לאחר אישור חשבון חלקי.',
        'שינויים בהיקף העבודה יתומחרו בנפרד בהסכמה בכתב.']
    tl=''.join(f'<li>{_e(t)}</li>' for t in terms)
    css=f'''
@page{{size:A4;margin:0}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:"Rubik","Assistant","Heebo","DejaVu Sans","Liberation Sans",sans-serif;color:#13213b;direction:rtl;font-size:10pt;-webkit-print-color-adjust:exact;print-color-adjust:exact}}
.pg{{width:210mm;min-height:297mm;page-break-after:always;position:relative;padding:18mm 16mm 20mm}}
.cover{{background:{NAVY};color:#fff;padding:0;overflow:hidden}}
.cover .grid{{position:absolute;inset:0;background-image:linear-gradient(rgba(92,176,255,.10) 1px,transparent 1px),linear-gradient(90deg,rgba(92,176,255,.10) 1px,transparent 1px);background-size:9mm 9mm;-webkit-mask-image:linear-gradient(160deg,#000 20%,transparent 75%)}}
.cover .glow{{position:absolute;width:150mm;height:150mm;border-radius:50%;left:-60mm;bottom:-50mm;background:radial-gradient(circle,rgba(31,111,209,.55),transparent 65%)}}
.cover .in{{position:relative;padding:22mm 20mm;height:297mm;display:flex;flex-direction:column}}
.top{{display:flex;justify-content:space-between;align-items:center}}
.lg{{width:56px;height:56px;border-radius:14px;background:{BLUE};display:grid;place-items:center;font-size:26pt;font-weight:700}}
.cn{{font-size:13pt;font-weight:600}}
.kick{{margin-top:58mm;color:{SKY};font-size:11pt;letter-spacing:3px;font-weight:500}}
.cover h1{{font-size:54pt;line-height:1.05;font-weight:700;margin:6mm 0 4mm}}
.cover h1 i{{font-style:normal;color:{SKY}}}
.cover .pj{{font-size:20pt;font-weight:300}}
.meta{{margin-top:auto;display:grid;grid-template-columns:repeat(4,1fr);border-top:1px solid rgba(255,255,255,.22);padding-top:7mm}}
.meta small{{display:block;font-size:8.5pt;color:{SKY};margin-bottom:2mm}} .meta b{{font-size:12pt;font-weight:500}}
.tot{{margin-top:10mm;background:rgba(255,255,255,.07);border:1px solid rgba(92,176,255,.35);border-radius:16px;padding:9mm 10mm;display:flex;justify-content:space-between;align-items:flex-end}}
.tot small{{color:{SKY};font-size:10pt}} .tot .v{{font-size:36pt;font-weight:700;line-height:1.1;margin-top:2mm}} .tot .s{{font-size:10pt;opacity:.8}}
h2.t{{font-size:20pt;color:{NAVY};font-weight:700;margin-bottom:2mm}} .sub{{color:#5b6b88;margin-bottom:5mm}}
.hd{{display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid {NAVY};padding-bottom:4mm;margin-bottom:8mm}}
.hd .l{{font-size:9pt;color:#5b6b88}}
.kp{{display:grid;grid-template-columns:repeat(3,1fr);gap:4mm;margin-bottom:8mm}}
.kp div{{border:1px solid #dbe3f0;border-radius:12px;padding:4mm;background:#f6f9ff}} .kp small{{color:#5b6b88;font-size:8.5pt}} .kp b{{display:block;font-size:17pt;color:{NAVY};margin-top:1mm}}
.dn{{display:flex;gap:10mm;align-items:center;margin-bottom:5mm}} .lgs{{flex:1}} .lgi{{display:flex;align-items:center;gap:3mm;padding:1.6mm 0;border-bottom:1px solid #eef2f8;font-size:9.5pt}} .lgi i{{width:9px;height:9px;border-radius:3px}} .lgi span{{flex:1}} .lgi b{{color:{NAVY}}}
table{{width:100%;border-collapse:collapse}}
.ct td{{padding:1mm 2mm;border-bottom:1px solid #eef2f8;font-size:9.5pt}} .ct .bar{{width:30%}} .ct .bar div{{height:7px;background:#eaf0fa;border-radius:4px;overflow:hidden}} .ct .bar span{{display:block;height:100%;background:linear-gradient(90deg,{BLUE},{SKY});border-radius:4px}}
.cd{{color:#7a8aa6;font-size:8.5pt;width:30px}} .num{{text-align:left;white-space:nowrap}} .sh{{color:#7a8aa6;width:44px}} .c{{text-align:center}} .b{{font-weight:600}}
.sum{{break-inside:avoid;margin-top:5mm;margin-right:auto;width:92mm;background:{NAVY};color:#fff;border-radius:14px;padding:5mm 6mm}} .sum div{{display:flex;justify-content:space-between;padding:1.4mm 0;font-size:10pt}} .sum .g{{border-top:1px solid rgba(255,255,255,.3);margin-top:2mm;padding-top:3mm;font-size:14pt;font-weight:700}}
.det{{padding-top:16mm;min-height:0}} .ch-h{{break-after:avoid;margin-top:4mm}} .ch-h{{display:flex;align-items:center;gap:4mm;background:{NAVY};color:#fff;border-radius:12px;padding:4mm 6mm;margin-bottom:5mm}} .ch-h span{{background:{BLUE};border-radius:8px;padding:1mm 3mm;font-size:10pt}} .ch-h h2{{flex:1;font-size:14pt;font-weight:600}}
.bq{{margin-bottom:6mm}} .bq .sb{{text-align:right;background:#e8f0fc;color:{NAVY};padding:2.4mm 3mm;font-size:10pt;border-radius:8px 8px 0 0}} .bq .th th{{font-size:8.5pt;color:#5b6b88;text-align:right;padding:2mm;border-bottom:1.5px solid {NAVY};font-weight:500}}
.bq td{{padding:2mm;font-size:9pt;border-bottom:1px solid #eef2f8;vertical-align:top}} .bq tbody tr:nth-child(even){{background:#fafcff}} .bq tr{{break-inside:avoid}}
.stt td{{background:#f0f5fd;font-weight:600;color:{NAVY};border-top:1.5px solid {BLUE}}}
.last ul{{padding-right:6mm;line-height:1.9;margin-bottom:12mm}}
.sig{{display:grid;grid-template-columns:1fr 1fr;gap:14mm;margin-top:18mm}} .sig div{{border-top:1.5px solid {NAVY};padding-top:3mm;color:#5b6b88;font-size:9pt}}
'''
    meta=f'<div><small>מספר הצעה</small><b dir="ltr">{_e(qno)}</b></div><div><small>תאריך</small><b>{today:%d.%m.%Y}</b></div><div><small>בתוקף עד</small><b>{(today+datetime.timedelta(days=valid)):%d.%m.%Y}</b></div><div><small>לכבוד</small><b>{_e(pr.get("client") or "—")}</b></div>'
    priced=sum(1 for c in chs for s in c['subs'] for i in s['items'] if i['price'])
    nitems=sum(c['n'] for c in chs)
    disc_row=f'<div><span>הנחה {dp:g}%</span><span dir="ltr">-{_n(disc_amt)}</span></div>' if dp else ''
    summary=f'''<section class="pg"><div class="hd"><b style="font-size:11pt">{_e(cname)}</b><div class="l">הצעת מחיר {_e(qno)} · {_e(pr["name"])}</div></div>
<h2 class="t">סיכום מנהלים</h2><div class="sub">התפלגות העלות לפי פרקי העבודה</div>
<div class="kp"><div><small>סה"כ לפני מע"מ</small><b dir="ltr">₪ {_n(net)}</b></div><div><small>סעיפים מתומחרים</small><b dir="ltr">{priced} / {nitems}</b></div><div><small>פרקי עבודה</small><b>{len(chs)}</b></div></div>
<div class="dn"><svg width="140" height="140" viewBox="0 0 180 180" style="width:140px;height:140px">{arcs}<text x="90" y="86" text-anchor="middle" font-size="11" fill="#5b6b88">סה"כ</text><text x="90" y="106" text-anchor="middle" font-size="16" font-weight="700" fill="{NAVY}">₪{_n(sub_total/1000)}K</text></svg><div class="lgs">{legend}</div></div>
<table class="ct">{ctab}</table>
<div class="sum"><div><span>סה"כ כתב כמויות</span><span dir="ltr">{_n(sub_total)}</span></div>{disc_row}<div><span>מע"מ {vat_p:g}%</span><span dir="ltr">{_n(vat)}</span></div><div class="g"><span>סה"כ לתשלום</span><span dir="ltr">₪ {_n(gross)}</span></div></div></section>'''
    last=f'''<section class="pg last"><div class="hd"><b style="font-size:11pt">{_e(cname)}</b><div class="l">הצעת מחיר {_e(qno)}</div></div><h2 class="t">תנאים והבהרות</h2><div class="sub">נא לעיין לפני אישור ההצעה</div><ul>{tl}</ul>
<div class="sig"><div>חתימה וחותמת — {_e(cname)}</div><div>אישור הלקוח — {_e(pr.get("client") or "שם הלקוח")} · תאריך</div></div></section>'''
    cover=f'''<section class="pg cover"><div class="grid"></div><div class="glow"></div><div class="in"><div class="top"><div class="cn">{_e(cname)}</div>{logo_html}</div>
<div class="kick">QUOTATION · הצעת מחיר</div><h1>הצעת<br><i>מחיר</i></h1><div class="pj">{_e(pr["name"])}</div>
<div class="meta">{meta}</div>
<div class="tot"><div><small>סה"כ הצעה כולל מע"מ</small><div class="v" dir="ltr">₪ {_n(gross)}</div></div><div class="s">לפני מע"מ<br><b dir="ltr">₪ {_n(net)}</b></div></div></div></section>'''
    body=f'{cover}{summary}<section class="pg det">{det}</section>{last}'
    if parts: return css,body
    return f'<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8"><style>{css}</style><body>{body}</body></html>'

def wrap(css,body):
    return f'<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8"><style>{css}</style><body>{body}</body></html>'

def render_pdf(html_str,out):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b=p.chromium.launch(); pg=b.new_page(); pg.set_content(html_str); pg.wait_for_timeout(300)
        pg.pdf(path=out,format='A4',print_background=True,margin=dict(top='0',bottom='0',left='0',right='0'),display_header_footer=True,
               header_template='<span></span>',footer_template='<div style="width:100%;font-size:8px;color:#7a8aa6;padding:0 16mm;display:flex;justify-content:space-between;direction:ltr"><span>MIDA</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')
        b.close()
