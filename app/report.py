"""Full calculation report: for every measured item, how it was calculated and where in the plans it comes from.
Each item shows its method, the formula, every element with dimensions, the checks, and a crop of the source sheet with the
elements numbered to match the table. Nothing is priced here."""
import base64, collections, html, io, os, pymupdf as fitz
from PIL import Image, ImageDraw, ImageFont

from .classify import TYPES
COL=[(214,40,40),(0,110,200),(20,140,60),(200,110,0),(130,50,170),(0,150,150),(190,60,110),(90,90,90)]
def _font(sz):
    for p in ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf','/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf'):
        if os.path.exists(p): return ImageFont.truetype(p,sz)
    return ImageFont.load_default()

def crop(path,locs,maxw=1100):
    """render the region that contains all locs (unrotated page coords) and draw numbered boxes. locs: [(num, [x0,y0,x1,y1])]"""
    pg=fitz.open(path)[0]; M=pg.rotation_matrix
    rs=[(n,fitz.Rect(*r)*M) for n,r in locs]
    U=fitz.Rect(1e9,1e9,-1e9,-1e9)
    for _,r in rs: U|=r
    pad=max(40,max(U.width,U.height)*0.18); R=fitz.Rect(U.x0-pad,U.y0-pad,U.x1+pad,U.y1+pad)&pg.rect
    z=min(maxw/R.width,3.0)
    pm=pg.get_pixmap(matrix=fitz.Matrix(z,z),clip=R,alpha=False)
    im=Image.frombytes('RGB',(pm.width,pm.height),pm.samples); d=ImageDraw.Draw(im); f=_font(max(14,int(im.width/55)))
    for n,r in rs:
        c=COL[(n-1)%len(COL)]; b=[(r.x0-R.x0)*z,(r.y0-R.y0)*z,(r.x1-R.x0)*z,(r.y1-R.y0)*z]
        d.rectangle(b,outline=c,width=max(3,int(im.width/300)))
        tw=f.getbbox(str(n)); w=tw[2]-tw[0]+10; h=tw[3]-tw[1]+8
        d.rectangle([b[0],b[1]-h,b[0]+w,b[1]],fill=c); d.text((b[0]+5,b[1]-h+2),str(n),fill='white',font=f)
    bio=io.BytesIO(); im.save(bio,'PNG',optimize=True); return bio.getvalue()

def item_images(pr,files_dir,tr,maxw=1100):
    """-> (list of (caption, png bytes), rows with their numbering). Rows with locs get numbers 1..n"""
    sheets={s['sid']:s for s in pr['sheets']}; per=collections.OrderedDict(); n=0; numbered=[]
    for r in tr.get('rows',[]):
        nums=[]
        for lc in r.get('locs') or []:
            n+=1; nums.append(n); per.setdefault(lc['sid'],[]).append((n,lc['r']))
        numbered.append((r,nums))
    imgs=[]
    for sid,locs in per.items():
        p=os.path.join(files_dir,sid+'.pdf')
        if not os.path.exists(p): continue
        try: imgs.append((f"גיליון {pr['sheets'].index(sheets[sid])+1} · {TYPES.get(sheets[sid].get('type'),'')}",crop(p,locs,maxw)))
        except Exception: pass
    return imgs,numbered

def _e(x): return html.escape(str(x if x is not None else ''))
def _nf(v,d=2):
    try: return f'{float(v):,.{d}f}'.rstrip('0').rstrip('.') if d else f'{float(v):,.0f}'
    except Exception: return _e(v)

CSS='''
@page{size:A4;margin:14mm 12mm 16mm}
*{box-sizing:border-box}body{font:11px/1.5 "Heebo","Assistant","Noto Sans Hebrew","DejaVu Sans",Arial,sans-serif;color:#1B2433;margin:0;direction:rtl}
h1{font-size:26px;margin:0 0 4px;color:#0D2A5C}h2{font-size:17px;margin:22px 0 8px;color:#0D43A0;border-bottom:2px solid #0D43A0;padding-bottom:4px;page-break-after:avoid}
h3{font-size:13px;margin:0}small,.mu{color:#6A7690}.cover{padding:40mm 0 0}.cover .sub{font-size:14px;color:#445}
table{width:100%;border-collapse:collapse}th{background:#EEF3FA;text-align:right;font-weight:600;padding:5px 7px;border-bottom:1px solid #C9D3E3}td{padding:5px 7px;border-bottom:1px solid #E6EBF3;vertical-align:top}
.num{direction:ltr;text-align:left;white-space:nowrap}.card{border:1px solid #D3DBE8;border-radius:8px;margin:0 0 14px;page-break-inside:avoid;overflow:hidden}
.card .hd{background:#F4F7FB;padding:8px 11px;display:flex;justify-content:space-between;gap:12px}.card .bd{padding:9px 11px}
.q{font-size:18px;font-weight:700;color:#0D2A5C;white-space:nowrap}.tag{display:inline-block;border-radius:10px;padding:1px 8px;font-size:10px;font-weight:600}
.t-ok{background:#E3F4EA;color:#1E6B45}.t-w{background:#FFF3D1;color:#8A6200}.t-b{background:#FBE3E3;color:#9B2323}
.fx{background:#F4F7FB;border-radius:6px;padding:6px 9px;margin:6px 0}.chk{margin:3px 0}.ok{color:#1E6B45}.bad{color:#9B2323}
.img{margin-top:8px}.img img{width:100%;max-height:155mm;object-fit:contain;border:1px solid #D3DBE8;border-radius:4px;background:#fff}.img small{display:block;margin-top:2px}
.nb{display:inline-block;min-width:17px;height:17px;border-radius:9px;color:#fff;font-size:9.5px;font-weight:700;text-align:center;line-height:17px;margin-left:3px}
.miss td:first-child{width:75px}.pb{page-break-before:always}.kv td:first-child{width:140px;color:#6A7690}
'''

def build(pr,files_dir,params=None,maxw=1100):
    rows=pr.get('boq') or []
    sheets=pr['sheets']; out=[]
    out.append(f"<div class='cover'><h1>דוח חישוב כמויות</h1><div class='sub'>{_e(pr['name'])}</div><p class='mu'>הדוח מפרט לכל סעיף איך חושבה הכמות, על מה היא מבוססת ובאיזה מקום בתוכנית. כל הכמויות הן נטו, מותקן, בלי תוספת פחת, אלא אם נאמר אחרת בסעיף. אין בדוח מחירים.</p>")
    cnt=collections.Counter(r['st'] if r.get('q') is not None else 'חסר' for r in rows if r['kind']=='item')
    out.append(f"<table class='kv' style='margin-top:18px'><tr><td>גרסה</td><td>{_e(pr.get('version',1))}</td></tr><tr><td>סעיפים בכתב</td><td>{sum(cnt.values())}</td></tr><tr><td>נמדדו</td><td>{cnt.get('נמדד',0)}</td></tr><tr><td>חלקיים</td><td>{cnt.get('חלקי',0)}</td></tr><tr><td>הוזנו ידנית</td><td>{cnt.get('ידני',0)}</td></tr><tr><td>חסרים</td><td>{cnt.get('חסר',0)+cnt.get('דורש השלמה',0)}</td></tr></table></div>")
    out.append("<h2 class='pb'>גיליונות בתיק</h2><table><tr><th>#</th><th>גיליון</th><th>סוג שזוהה</th><th>קומה</th></tr>"+''.join(f"<tr><td>{i+1}</td><td>{_e(s['file'][9:70])}</td><td>{_e(s.get('type'))}</td><td>{_e(s.get('floor') or '')}</td></tr>" for i,s in enumerate(sheets))+"</table>")
    if params:
        out.append("<h2>פרמטרים והנחות</h2><table>"+''.join(f"<tr><td>{_e(k)}</td><td class='num'>{_e(v)}</td></tr>" for k,v in params)+"</table>")
    # chapter summary
    chs=[]; cur=None
    for r in rows:
        if r['kind']=='ch' and r['desc']!=pr['name']: cur=dict(code=r['code'][:2],name=r['desc'],items=[]); chs.append(cur)
        elif r['kind']=='item' and cur is not None: cur['items'].append(r)
    out.append("<h2>סיכום לפי פרקים</h2><table><tr><th>פרק</th><th>שם</th><th>סעיפים</th><th>עם חישוב מפורט</th><th>חלקיים</th><th>חסרים</th></tr>"+''.join(f"<tr><td>{c['code']}</td><td>{_e(c['name'])}</td><td>{len(c['items'])}</td><td>{sum(1 for i in c['items'] if i.get('trace'))}</td><td>{sum(1 for i in c['items'] if i.get('q') is not None and i['st']=='חלקי')}</td><td>{sum(1 for i in c['items'] if i.get('q') is None)}</td></tr>" for c in chs if c['items'])+"</table>")
    later=[]
    for c in chs:
        meas=[i for i in c['items'] if i.get('q') is not None]; miss=[i for i in c['items'] if i.get('q') is None]
        if not meas and not miss: continue
        if not meas: later.append((c,miss)); continue
        out.append(f"<h2 class='pb'>פרק {c['code']} · {_e(c['name'])}</h2>")
        for it in meas:
            st=it['st']; tg='t-ok' if st=='נמדד' else 't-w'; tr=it.get('trace')
            body=''
            if it.get('method'): body+=f"<div><small>אופן המדידה לפי המפרט</small><div>{_e(it['method'])}{' <span class=\"tag t-ok\">כלל מאומת</span>' if it.get('vsrc')=='v' else ' <span class=\"tag t-w\">כלל לאימות</span>'}</div></div>"
            if tr:
                imgs,numbered=item_images(pr,files_dir,tr,maxw)
                body+=f"<div class='fx'><b>נוסחה:</b> {_e(tr.get('formula',''))}</div>"
                body+="<table><tr><th>#</th><th>אלמנט</th><th>מידות (מ')</th><th>כמות</th><th>מקור והערה</th></tr>"
                for r,nums in numbered:
                    tags=''.join(f"<span class='nb' style='background:rgb{COL[(n-1)%len(COL)]}'>{n}</span>" for n in nums)
                    body+=f"<tr><td>{tags}</td><td>{_e(r['el'])}</td><td class='num'>{_e(r.get('dims',''))}</td><td class='num'><b>{_nf(r['val'])}</b></td><td>{_e(r.get('src',''))}{('<br><small>'+_e(r['note'])+'</small>') if r.get('note') else ''}</td></tr>"
                body+=f"<tr><td></td><td><b>סה\"כ</b></td><td></td><td class='num'><b>{_nf(it['q'])}</b></td><td>{_e(it['unit'])}</td></tr></table>"
                if tr.get('params'): body+="<div class='mu' style='margin-top:4px'>פרמטרים: "+' · '.join(f"{_e(k)} = {_e(v)}" for k,v in tr['params'].items())+"</div>"
                seen=set()
                for ck in tr.get('checks',[]):
                    if ck['t'] in seen: continue
                    seen.add(ck['t']) body+=f"<div class='chk {'ok' if ck['ok'] else 'bad'}'>{'✓' if ck['ok'] else '⚠'} {_e(ck['t'])}</div>"
                for cap,png in imgs: body+=f"<div class='img'><img src='data:image/png;base64,{base64.b64encode(png).decode()}'><small>{_e(cap)}</small></div>"
            else:
                body+=f"<div class='fx'><b>מקור:</b> {_e(it.get('src',''))}</div><div class='mu'>לסעיף זה אין עדיין פירוט לפי אלמנט. מוצגים הסכום והמקור בלבד.</div>"
            if it.get('need'): body+=f"<div class='chk bad'>⚠ {_e(it['need'])}</div>"
            out.append(f"<div class='card'><div class='hd'><div><small>{_e(it['code'])}</small><h3>{_e(it.get('full') or it['desc'])}</h3><span class='tag {tg}'>{_e(st)}</span></div><div class='q'>{_nf(it['q'])} <small>{_e(it['unit'])}</small></div></div><div class='bd'>{body}</div></div>")
        if miss:
            out.append("<h3 style='margin:10px 0 4px'>סעיפים בלי כמות בפרק זה</h3><table class='miss'><tr><th>סעיף</th><th>תיאור</th><th>למה חסר</th></tr>"+''.join(f"<tr><td>{_e(i['code'])}</td><td>{_e(i['desc'])}</td><td>{_e(i.get('need',''))}</td></tr>" for i in miss)+"</table>")
    if later:
        out.append("<h2 class='pb'>פרקים שלא חושבו</h2><p class='mu'>לפרקים אלה אין כמויות כי חסרים הגיליונות הנדרשים. בכל שורה מצוין איזה גיליון חסר.</p>")
        for c,miss in later:
            out.append(f"<h3 style='margin:12px 0 4px'>פרק {c['code']} · {_e(c['name'])}</h3><table class='miss'><tr><th>סעיף</th><th>תיאור</th><th>למה חסר</th></tr>"+''.join(f"<tr><td>{_e(i['code'])}</td><td>{_e(i['desc'])}</td><td>{_e(i.get('need',''))}</td></tr>" for i in miss)+"</table>")
    return "<!doctype html><html lang='he' dir='rtl'><meta charset='utf-8'><style>"+CSS+"</style><body>"+''.join(out)+"</body></html>"

def to_pdf(html_text,out_path):
    import subprocess,tempfile,sys
    tmp=tempfile.NamedTemporaryFile('w',suffix='.html',delete=False,encoding='utf-8'); tmp.write(html_text); tmp.close()
    code=("from playwright.sync_api import sync_playwright;import sys\n"
          "with sync_playwright() as p:\n b=p.chromium.launch();pg=b.new_page();pg.goto('file://'+sys.argv[1]);pg.wait_for_timeout(500)\n"
          " pg.pdf(path=sys.argv[2],format='A4',print_background=True,margin=dict(top='14mm',bottom='16mm',left='12mm',right='12mm'),display_header_footer=True,header_template='<span></span>',footer_template='<div style=\"font-size:8px;width:100%;text-align:center;color:#778\"><span class=pageNumber></span> / <span class=totalPages></span></div>');b.close()")
    subprocess.run([sys.executable,'-c',code,tmp.name,out_path],check=True,timeout=300); os.remove(tmp.name)
