"""Builds kamuyot_engine_demo_v4.html from app_tpl_v4.html (adds the villa screen).
Usage: python3 build_v4.py <dir with extracted mnoa/ folder> <path to node_modules/@fontsource> <villa dir with villa.json and piles.jpg>
Fonts (free): npm i @fontsource/rubik @fontsource/assistant @fontsource/ibm-plex-mono
Data and images come from mnoa/system/data.json and mnoa/results/ inside mnoa_kamuyot.zip."""
import base64, json, io, os, sys
from PIL import Image
S=sys.argv[1]
R=S+'/mnoa/results'
F=sys.argv[2]
VD=sys.argv[3]
EMPTY=len(sys.argv)>4 and sys.argv[4]=='empty'
HERE=os.path.dirname(os.path.abspath(__file__))
HE='U+0590-05FF,U+200C-2010,U+20AA,U+25CC,U+FB1D-FB4F'
LA='U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+2000-206F,U+2074,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD'
specs=[('rubik','Rubik',[500,700],True),('assistant','Assistant',[400,600,700],True),('ibm-plex-mono','IBM Plex Mono',[400,500],False)]
css=[]
for pkg,fam,ws,he in specs:
    for w in ws:
        for sub,ur in ((('hebrew',HE),('latin',LA)) if he else (('latin',LA),)):
            b=base64.b64encode(open(f'{F}/{pkg}/files/{pkg}-{sub}-{w}-normal.woff2','rb').read()).decode()
            css.append(f"@font-face{{font-family:'{fam}';font-weight:{w};font-style:normal;font-display:swap;src:url(data:font/woff2;base64,{b}) format('woff2');unicode-range:{ur}}}")
def img(path,maxw=1500,q=80):
    im=Image.open(path).convert('RGB')
    if im.width>maxw: im=im.resize((maxw,round(im.height*maxw/im.width)),Image.LANCZOS)
    bio=io.BytesIO(); im.save(bio,'JPEG',quality=q,optimize=True)
    return 'data:image/jpeg;base64,'+base64.b64encode(bio.getvalue()).decode()
imgs={'pB':R+'/hofim/ov_B110.jpg','pC':R+'/hofim/ov_C110.jpg','walls':R+'/hofim/fig_walls_220.jpg','slab':R+'/hofim/fig_slab_220.jpg','ocr':R+'/hofim/fig_ocr230.jpg',
      'struct':R+'/olga/img_struct.jpg','arch':R+'/olga/img_arch.jpg','beam':R+'/olga/img_beam.jpg','ceil':R+'/olga/fig_ceil.jpg','faces':R+'/olga/fig_faces.jpg'}
IM={} if EMPTY else {k:img(v) for k,v in imgs.items()}
VILLA={'rows':[],'sheets':[],'needs':[],'boq':[]} if EMPTY else json.load(open(VD+'/villa.json',encoding='utf-8'))
if not EMPTY: IM['piles']=img(VD+'/piles.jpg',900,82)
d=json.load(open(S+'/mnoa/system/data.json',encoding='utf-8'))
keep=('id','name','place','client','scale','sheets','layers','chapters','chapters_scope','findings','gap_total','under_total','concrete','masonry','items','rebar','walls','slabs','piles','finishes')
slim={'stats':d['stats'],'projects':[{k:p[k] for k in keep if k in p} for p in d['projects']]}
if EMPTY: slim={'stats':{'sheets':0,'labels':0},'projects':[]}
t=open(HERE+'/app_tpl_v4.html',encoding='utf-8').read()
out=t.replace('{{FONTS}}','\n'.join(css)).replace('{{DATA}}',json.dumps(slim,ensure_ascii=False)).replace('{{IMGS}}',json.dumps(IM)).replace('{{VILLA}}',json.dumps(VILLA,ensure_ascii=False)).replace('{{EMPTY}}','true' if EMPTY else 'false')
# SCRUB: the empty system must not carry any project or client names
if EMPTY:
    for a,c in [('גן אולגה','פרויקט א׳'),('תיכון חופים','פרויקט ב׳'),('וילה איבגי','פרויקט'),('אולגה','א׳'),('חופים','ב׳'),('איבגי',''),('FARBER INGA','המהנדס'),('חדרה','העיר')]: out=out.replace(a,c)
open(HERE+'/../'+('kamuyot_system_empty.html' if EMPTY else 'kamuyot_engine_demo_v4.html'),'w',encoding='utf-8').write(out)
print(len(out)//1024,'KB')
