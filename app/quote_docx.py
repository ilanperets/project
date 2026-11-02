"""Edited quote HTML -> .docx (pandoc, then RTL/Hebrew/tables polish with python-docx)."""
import re, subprocess, os
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

def _clean(h):
    h=re.sub(r'<svg.*?</svg>','',h,flags=re.S)
    h=re.sub(r'<table class="bq"><thead><tr><th colspan="6"[^>]*>(.*?)</th></tr>(<tr class="th">.*?</tr>)</thead><tbody>',lambda m:'<h3>'+m.group(1)+'</h3><table><tbody>'+m.group(2),h,flags=re.S)
    h=re.sub(r'<td colspan="5">(.*?)</td>',r'<td>\1</td><td></td><td></td><td></td><td></td>',h)
    h=re.sub(r'<div class="ch-h">(.*?)</div>',lambda m:'<h2>'+re.sub(r'<[^>]+>',' ',m.group(1))+'</h2>',h,flags=re.S)
    h=re.sub(r'<div class="(grid|glow)"></div>','',h)
    h=re.sub(r'<div class="bar">.*?</div>','',h)
    h=re.sub(r'<td class="bar">.*?</td>','',h,flags=re.S)
    h=re.sub(r' (style|class|contenteditable|dir)="[^"]*"','',h)
    return '<html><body>'+h+'</body></html>'

def _rtl(p):
    pPr=p._p.get_or_add_pPr()
    if pPr.find(qn('w:bidi')) is None: pPr.append(OxmlElement('w:bidi'))
    for r in p.runs:
        rPr=r._r.get_or_add_rPr()
        if rPr.find(qn('w:rtl')) is None: rPr.append(OxmlElement('w:rtl'))
        r.font.name='Arial'; rPr.rFonts.set(qn('w:cs'),'Arial')

def html_to_docx(body,out,workdir):
    src=os.path.join(workdir,'q.html'); raw=os.path.join(workdir,'raw.docx')
    open(src,'w',encoding='utf-8').write(_clean(body))
    subprocess.run(['pandoc',src,'-f','html','-t','docx','-o',raw],check=True,timeout=120)
    d=Document(raw)
    for s in d.sections: s.right_margin=s.left_margin=Cm(1.8)
    for p in d.paragraphs: _rtl(p)
    navy=RGBColor(0x04,0x1A,0x3F)
    for p in d.paragraphs:
        if p.style.name.startswith('Heading'):
            for r in p.runs: r.font.color.rgb=navy; r.font.bold=True
    for t in d.tables:
        tblPr=t._tbl.tblPr
        if tblPr.find(qn('w:bidiVisual')) is None: tblPr.append(OxmlElement('w:bidiVisual'))
        b=OxmlElement('w:tblBorders')
        for e in ('top','left','bottom','right','insideH','insideV'):
            x=OxmlElement('w:'+e); x.set(qn('w:val'),'single'); x.set(qn('w:sz'),'4'); x.set(qn('w:color'),'D5DEEC'); b.append(x)
        tblPr.append(b)
        if len(t.columns)==6:
            t.autofit=False; W=[2.0,8.2,1.3,1.6,1.9,2.4]
            tp=t._tbl.tblPr; lay=OxmlElement('w:tblLayout'); lay.set(qn('w:type'),'fixed'); tp.append(lay)
            grid=t._tbl.tblGrid
            for gc,w in zip(grid.findall(qn('w:gridCol')),W): gc.set(qn('w:w'),str(int(w*567)))
            for row in t.rows:
                for c,w in zip(row.cells,W): c.width=Cm(w)
        for row in t.rows:
            for c in row.cells:
                for p in c.paragraphs:
                    _rtl(p)
                    for r in p.runs: r.font.size=Pt(9)
    d.save(out)
