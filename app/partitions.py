"""New partitions in renovation plans: drawn as unfilled double lines on a wall layer (existing walls are solid black fills).
Centre-line length = stroke length / 2; area = length x height."""
import math, pymupdf
def new_partitions(path,scale=50,layers=None):
    pg=pymupdf.open(path)[0]; k=25.4/72*scale/1000.0; tot=0.0; n=0
    for d in pg.get_drawings():
        ly=(d.get('layer') or '')
        if (layers is not None and ly not in layers) or (layers is None and 'WALL' not in ly.upper()) or d.get('fill') is not None or d['type']!='s': continue
        for it in d['items']:
            if it[0]=='l': tot+=math.dist(it[1],it[2])*k; n+=1
            elif it[0]=='re': r=it[1]; tot+=2*(r.width+r.height)*k; n+=1
            elif it[0]=='qu': q=it[1].rect; tot+=2*(q.width+q.height)*k; n+=1
    if n<10: return None
    return dict(length_m=round(tot/2,1),strokes=n)
