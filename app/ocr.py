"""Hebrew OCR for sheets whose text is drawn as outlines (no text layer). Tesseract + the open-source (Apache-2.0) heb model in app/tessdata."""
import os, re, pymupdf
from PIL import Image
TESS=os.path.join(os.path.dirname(os.path.abspath(__file__)),'tessdata')
def available():
    try:
        import pytesseract; pytesseract.get_tesseract_version(); return os.path.exists(os.path.join(TESS,'heb.traineddata'))
    except Exception: return False
def _img(pg,zoom,clip=None):
    pm=pg.get_pixmap(matrix=pymupdf.Matrix(zoom,zoom),colorspace=pymupdf.csGRAY,clip=clip)
    return Image.frombytes('L',(pm.width,pm.height),pm.samples)
def lines(path,zoom=1.5,psm=11,timeout=45,maxpx=4500):
    """-> list of dict(text,x,y,w,h) in PDF points (line level)"""
    import pytesseract, json, hashlib
    st=os.stat(path); ck=os.path.join(os.path.dirname(path),'.ocr_'+hashlib.md5(f"{os.path.basename(path)}|{st.st_size}|{st.st_mtime_ns}|{zoom}|{psm}".encode()).hexdigest()+'.json')
    try: return json.load(open(ck))
    except Exception: pass
    pg=pymupdf.open(path)[0]; zoom=min(zoom,maxpx/max(pg.rect.width,pg.rect.height)); im=_img(pg,zoom)
    d=pytesseract.image_to_data(im,lang='heb',config=f'--tessdata-dir {TESS} --psm {psm}',output_type=pytesseract.Output.DICT,timeout=timeout)
    rows={}
    for i,t in enumerate(d['text']):
        t=(t or '').strip()
        if not t or float(d['conf'][i])<35: continue
        k=(d['block_num'][i],d['par_num'][i],d['line_num'][i]); rows.setdefault(k,[]).append((d['left'][i],d['top'][i],d['width'][i],d['height'][i],t))
    out=[]
    for ws in rows.values():
        ws.sort(key=lambda w:-w[0])      # right to left for Hebrew
        x0=min(w[0] for w in ws); y0=min(w[1] for w in ws); x1=max(w[0]+w[2] for w in ws); y1=max(w[1]+w[3] for w in ws)
        out.append(dict(text=' '.join(w[4] for w in ws),x=x0/zoom,y=y0/zoom,w=(x1-x0)/zoom,h=(y1-y0)/zoom))
    try: json.dump(out,open(ck,'w'),ensure_ascii=False)
    except Exception: pass
    return out
def text(path,**k): return '\n'.join(l['text'] for l in lines(path,**k))

def title_block(path,zoom=3.0):
    """OCR only the title block (lower-right corner of the sheet), where drawing names are usually written. Cached."""
    import pytesseract, json, hashlib
    st=os.stat(path); ck=os.path.join(os.path.dirname(path),'.ocrt_'+hashlib.md5(f"{os.path.basename(path)}|{st.st_size}|{st.st_mtime_ns}|{zoom}".encode()).hexdigest()+'.json')
    try: return json.load(open(ck))
    except Exception: pass
    pg=pymupdf.open(path)[0]; r=pg.rect
    clip=pymupdf.Rect(r.x0+r.width*0.80,r.y0+r.height*0.78,r.x1,r.y1)
    zoom=min(zoom,3500/max(clip.width,clip.height))
    im=_img(pg,zoom,clip)
    out=pytesseract.image_to_string(im,lang='heb',config=f'--tessdata-dir {TESS} --psm 6',timeout=40)
    try: json.dump(out,open(ck,'w'),ensure_ascii=False)
    except Exception: pass
    return out
