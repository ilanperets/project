"""Element calculators: pure functions the brain uses to turn plan measurements into BOQ quantities.
Every rule is common practice written in our own words (src 'g') unless noted; thresholds such as the
opening-deduction limit are parameters, to be fixed against the Blue Book text of the specific tender."""
import math

DEFAULTS=dict(open_ded_m2=0.5, roof_open_ded_m2=0.25, waste_tile=0.10, waste_paint=0.0, waste_block=0.05,
              swell=1.25, shrink=0.90, block_per_m2=12.5, duct_waste=0.0)

# slope multiplier = 1/cos(theta); slope given as degrees or percent
def slope_factor(deg=None,pct=None):
    if pct is not None: deg=math.degrees(math.atan(pct/100))
    return 1/math.cos(math.radians(deg or 0))

def roof_sloped_area(plan_m2,deg=None,pct=None):
    """Pitched roof surface from its plan (horizontal) area."""
    return plan_m2*slope_factor(deg,pct)

def rafter_length(run_m,deg=None,pct=None):
    return run_m*slope_factor(deg,pct)

def tiles_roof(sloped_m2,per_m2=12.0,waste=0.05):
    """Roof tiles count; per_m2 comes from the tile product sheet (typically 10-16)."""
    return math.ceil(sloped_m2*per_m2*(1+waste))

def net_wall_area(length_m,height_m,openings,limit=None):
    """Wall area net of openings larger than the limit (m2 each). openings = list of (w,h)."""
    limit=DEFAULTS['open_ded_m2'] if limit is None else limit
    ded=sum(w*h for w,h in openings if w*h>limit)
    return max(length_m*height_m-ded,0)

def plaster_area(wall_area_m2,both_sides=False):
    return wall_area_m2*(2 if both_sides else 1)

def paint_area(room_perimeter_m,height_m,ceiling_m2,openings=(),limit=None):
    return net_wall_area(room_perimeter_m,height_m,openings,limit)+ceiling_m2

def floor_tile(room_m2,waste=None):
    return room_m2*(1+(DEFAULTS['waste_tile'] if waste is None else waste))

def skirting(perimeter_m,door_widths=()):
    return max(perimeter_m-sum(door_widths),0)

def drywall_area(length_m,height_m,sides=1,openings=(),limit=None):
    return net_wall_area(length_m,height_m,openings,limit)*sides

def waterproof_wet_room(floor_m2,perimeter_m,rise_m=0.2,door_widths=()):
    """Wet-room waterproofing: floor net plus upstand (20 cm) along the walls, minus door widths."""
    return floor_m2+(perimeter_m-sum(door_widths))*rise_m

def waterproof_roof(plan_m2,parapet_len_m,parapet_h_m=0.3):
    return plan_m2+parapet_len_m*parapet_h_m

def blocks(wall_area_m2,per_m2=None,waste=None):
    return math.ceil(wall_area_m2*(DEFAULTS['block_per_m2'] if per_m2 is None else per_m2)*(1+(DEFAULTS['waste_block'] if waste is None else waste)))

def concrete_volume(l,w,h,n=1): return l*w*h*n
def slab_volume(area_m2,thick_m): return area_m2*thick_m
def formwork_beam(length_m,width_m,depth_m,soffit=True): return length_m*(2*depth_m+(width_m if soffit else 0))
def formwork_column(h_m,w_m,d_m): return h_m*2*(w_m+d_m)
def rebar_tons(volume_m3,kg_per_m3): return volume_m3*kg_per_m3/1000
def rebar_kg_per_m(d_mm): return d_mm*d_mm/162.0   # theoretical steel weight per metre

# --- earthworks ---
def trench_volume(length_m,width_m,depth_m): return length_m*width_m*depth_m
def excavation_prism(area_m2,avg_depth_m): return area_m2*avg_depth_m
def loose_volume(bank_m3,swell=None): return bank_m3*(DEFAULTS['swell'] if swell is None else swell)
def compacted_fill(bank_m3,shrink=None): return bank_m3/(DEFAULTS['shrink'] if shrink is None else shrink)
def cut_fill_balance(cut_m3,fill_m3,swell=None,shrink=None):
    """Positive = surplus to haul away (loose m3), negative = soil to import (bank m3)."""
    avail=cut_m3; need=fill_m3
    return (avail-need*(DEFAULTS['shrink'] if shrink is None else shrink))*(DEFAULTS['swell'] if swell is None else swell)

# --- site development ---
def paving_area(area_m2,waste=0.05): return area_m2*(1+waste)
def curb_length(perimeter_m,gaps=()): return max(perimeter_m-sum(gaps),0)
def fence_posts(length_m,spacing_m=2.5): return math.ceil(length_m/spacing_m)+1
def fence_panels(length_m,panel_m=2.5): return math.ceil(length_m/panel_m)
def retaining_wall_concrete(length_m,height_m,thick_m,footing_w_m,footing_t_m):
    return length_m*(height_m*thick_m+footing_w_m*footing_t_m)
def topsoil(area_m2,thick_m): return area_m2*thick_m
def irrigation_pipe(zones_m): return sum(zones_m)

# --- drainage / sewer / manholes ---
def pipe_run(points):
    """points = [(x,y),...] in metres along the pipe route; returns length in m."""
    return sum(math.dist(a,b) for a,b in zip(points,points[1:]))
def manhole_depth(cover_level,invert_level): return cover_level-invert_level
def manhole_count(runs_m,max_spacing_m=40,changes=0): return sum(math.ceil(r/max_spacing_m) for r in runs_m)+changes
def trench_for_pipe(length_m,dia_m,depth_m,bedding_m=0.15,extra_w_m=0.6):
    w=dia_m+extra_w_m; return dict(excavation_m3=length_m*w*(depth_m),bedding_m3=length_m*w*(bedding_m+dia_m*0.3))
def pipe_slope_pct(drop_m,length_m): return drop_m/length_m*100 if length_m else 0

# --- HVAC ---
def duct_area(w_m,h_m,length_m): return 2*(w_m+h_m)*length_m
def round_duct_area(dia_m,length_m): return math.pi*dia_m*length_m
def duct_insulation(area_m2,layers=1): return area_m2*layers

# --- pergola ---
def pergola(length_m,width_m,post_spacing_m=3.0,beam_spacing_m=0.5):
    posts=(math.ceil(length_m/post_spacing_m)+1)*2
    beams=math.ceil(length_m/beam_spacing_m)+1
    return dict(posts=posts,beams=beams,beam_total_m=beams*width_m,main_girder_m=2*length_m,roof_m2=length_m*width_m)

# --- electrical ---
def cable_run(path_m,slack=0.1): return path_m*(1+slack)

RULES=[  # (id, text) shown in the brain screen
('open_ded','פתחים נוכים משטח קירות רק מעל סף (ברירת מחדל 0.5 מ"ר בשטח, 0.25 בגגות) - לאימות מול הספר'),
('slope','שטח גג משופע = שטח במבט על ÷ cos(זווית השיפוע)'),
('wet_room','איטום חדר רטוב = רצפה נטו + עליית 20 ס"מ על הקירות, בניכוי רוחב דלת'),
('duct','שטח תעלת מיזוג מלבנית = 2 × (רוחב + גובה) × אורך'),
('swell','פחת/ניפוח עפר: נפח מפורק גדול מנפח במקום (ברירת מחדל ×1.25), מהודק קטן (×0.9) - תלוי סוג קרקע'),
('pipe','צנרת נמדדת לפי אורך מותקן; קשתות, מופות ואטמים כלולים במחיר (מקור: מפרט עירוני שנקרא)'),
('net','כמויות נמדדות נטו, מותקן באתר, ללא תוספת פחת (מקור: מפרט עירוני שנקרא)'),
]
