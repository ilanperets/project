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
def lines(path,zoom=1.5,psm=11,timeout=240):
    """-> list of dict(text,x,y,w,h) in PDF points (line level)"""
    import pytesseract
    pg=pymupdf.open(path)[0]; im=_img(pg,zoom)
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
    return out
def text(path,**k): return '\n'.join(l['text'] for l in lines(path,**k))
