"""Word-style quote editor page (served per project; talks to /api/projects/{pid}/quote_doc*)."""
TOOLBAR='''
<div class="rb"><div class="tt"><b>עריכת הצעת מחיר</b><span id="sv" style="opacity:.7">· נשמר</span><span class="sp"></span>
<button class="g" onclick="document.execCommand('undo')">↶ בטל</button><button class="g" onclick="document.execCommand('redo')">↷ בצע שוב</button>
<button class="g" onclick="st()">⚙ הגדרות</button><button class="g" onclick="refresh()">רענן נתונים</button><button class="g" onclick="reset()">שחזר מקור</button>
<button class="g" onclick="exp('docx')">⬇ Word</button><button class="g" onclick="exp('pdf')">⬇ PDF</button><button class="g" onclick="parent.postMessage('qed-close','*')">✕ סגור</button></div>
<div class="tl">
<div class="gp"><select onchange="c('fontName',this.value)"><option>Rubik</option><option>Assistant</option><option>Arial</option><option>David</option><option>Times New Roman</option><option>Tahoma</option></select>
<select onchange="c('fontSize',this.value)"><option value="1">קטן</option><option value="2">9</option><option value="3" selected>10</option><option value="4">13</option><option value="5">18</option><option value="6">24</option><option value="7">32</option></select></div>
<div class="gp"><button class="t" onclick="c('bold')"><b>B</b></button><button class="t" onclick="c('italic')"><i>I</i></button><button class="t" onclick="c('underline')"><u>U</u></button><button class="t" onclick="c('strikeThrough')"><s>S</s></button>
<small>צבע</small><input type="color" value="#041A3F" onchange="c('foreColor',this.value)"><small>סימון</small><input type="color" value="#fff3a3" onchange="c('hiliteColor',this.value)"></div>
<div class="gp"><button class="t" onclick="c('justifyRight')">ימין</button><button class="t" onclick="c('justifyCenter')">מרכז</button><button class="t" onclick="c('justifyLeft')">שמאל</button><button class="t" onclick="c('justifyFull')">יישור</button></div>
<div class="gp"><button class="t" onclick="c('insertUnorderedList')">• רשימה</button><button class="t" onclick="c('insertOrderedList')">1. מספור</button><button class="t" onclick="c('outdent')">⇤</button><button class="t" onclick="c('indent')">⇥</button></div>
<div class="gp"><button class="t" onclick="tbl()">▦ טבלה</button><button class="t" onclick="rw()">+ שורה</button><button class="t" onclick="rd()">− שורה</button><button class="t" onclick="cl()">+ עמודה</button><button class="t" onclick="document.getElementById('im').click()">🖼 תמונה / לוגו</button><input id="im" type="file" accept="image/*" hidden onchange="img(this)"></div>
<div class="gp"><button class="t" onclick="c('insertHorizontalRule')">― קו</button><button class="t" onclick="c('removeFormat')">נקה עיצוב</button><button class="t" onclick="c('insertHTML','<div style=&quot;break-after:page&quot;></div>')">⤓ מעבר עמוד</button><button class="t" onclick="c('formatBlock','h2')">כותרת</button></div>
</div></div>
<div id="stp" hidden><div class="sb"><h3>הגדרות הצעה</h3>
<label>שם החברה<input id="s_name"></label><label>לוגו<input type="file" id="s_logo" accept="image/*"></label>
<label>הנחה %<input id="s_disc" type="number" min="0" max="100" step="0.5"></label><label>מע"מ %<input id="s_vat" type="number" min="0" max="30"></label>
<label>תוקף (ימים)<input id="s_valid" type="number" min="1" max="365"></label>
<div class="mu">שינוי הגדרות בונה את ההצעה מחדש, ועריכות ידניות יידרסו.</div>
<div style="display:flex;gap:8px"><button class="g2" onclick="saveSt()">שמור ובנה מחדש</button><button class="g3" onclick="st()">ביטול</button></div></div></div>'''
EXTRA_CSS='''
body{background:#e9eef6;padding-top:132px;margin:0}
.pg{margin:18px auto;box-shadow:0 6px 30px rgba(4,26,63,.18);background:#fff;page-break-after:auto}
.cover{background:#041A3F}
.rb{position:fixed;top:0;right:0;left:0;z-index:9;background:#fff;border-bottom:1px solid #d5deec;font-family:Rubik,Assistant,Arial,sans-serif;direction:rtl}
.tt{display:flex;align-items:center;gap:8px;padding:8px 16px;background:#041A3F;color:#fff;font-size:14px;flex-wrap:wrap}
.tt .sp{flex:1}.tt button{border:0;border-radius:8px;padding:7px 12px;font:600 13px Rubik,Assistant,Arial;cursor:pointer;background:#1F6FD1;color:#fff}.tt button.g{background:rgba(255,255,255,.14)}
.tl{display:flex;flex-wrap:wrap;gap:4px 10px;padding:8px 14px;align-items:center}
.gp{display:flex;gap:2px;align-items:center;padding:0 10px;border-left:1px solid #e3e9f3}.gp:last-child{border:0}
.rb button.t,.rb select,.rb input[type=color]{height:32px;min-width:32px;border:1px solid transparent;background:#fff;border-radius:7px;font:500 14px Rubik,Assistant,Arial;color:#041A3F;cursor:pointer;padding:0 8px}
.rb button.t:hover{background:#eaf2fd}.rb select{border-color:#d5deec}.rb input[type=color]{padding:2px;width:34px;border-color:#d5deec}
.rb small{font-size:10.5px;color:#7a8aa6;margin-right:4px}
.pg:focus-within{box-shadow:0 0 0 2px #5CB0FF,0 6px 30px rgba(4,26,63,.18)}.pg [contenteditable]:focus,.pg:focus{outline:none}
td:focus,th:focus{outline:2px solid #5CB0FF}
#stp{position:fixed;inset:0;z-index:20;background:rgba(4,26,63,.5);display:grid;place-items:center;font-family:Rubik,Assistant,Arial}
#stp[hidden]{display:none}.sb{background:#fff;border-radius:16px;padding:22px;width:360px;display:grid;gap:10px;direction:rtl}
.sb h3{margin:0;color:#041A3F}.sb label{display:grid;gap:4px;font-size:13px;color:#5b6b88}.sb input{border:1px solid #d5deec;border-radius:8px;padding:8px;font:inherit}.mu{font-size:12px;color:#7a8aa6}
.g2{flex:1;background:#1F6FD1;color:#fff;border:0;border-radius:8px;padding:9px;font:600 14px Rubik,Assistant;cursor:pointer}.g3{border:1px solid #d5deec;background:#fff;border-radius:8px;padding:9px 14px;cursor:pointer;font:600 14px Rubik,Assistant}
@media print{.rb{display:none}body{padding:0;background:#fff}.pg{margin:0;box-shadow:none}}
'''
JS='''
const API='/api/projects/%PID%';let tm=null,CSS='';
const $=s=>document.querySelector(s);
function c(k,v){document.execCommand(k,false,v||null)}
function cell(){let n=getSelection().anchorNode;while(n&&!(n.nodeName=='TD'||n.nodeName=='TH'))n=n.parentNode;return n}
function tbl(){const td='<td style="border:1px solid #cfd9ea;padding:6px">&nbsp;</td>';c('insertHTML','<table style="width:100%;border-collapse:collapse"><tr>'+td+td+td+'</tr><tr>'+td+td+td+'</tr></table><br>')}
function rw(){let t=cell();if(!t)return;let r=t.parentNode,n=r.cloneNode(true);n.querySelectorAll('td,th').forEach(x=>x.innerHTML='&nbsp;');r.after(n)}
function rd(){let t=cell();if(t)t.parentNode.remove()}
function cl(){let t=cell();if(!t)return;let i=[...t.parentNode.children].indexOf(t);t.closest('table').querySelectorAll('tr').forEach(r=>{let x=r.children[i];if(x){let n=x.cloneNode(false);n.innerHTML='&nbsp;';x.after(n)}})}
function img(i){let f=i.files[0];if(!f)return;let r=new FileReader();r.onload=()=>c('insertHTML','<img src="'+r.result+'" style="max-width:60mm">');r.readAsDataURL(f)}
function body(){return $('#doc').innerHTML}
function load(d){CSS=d.css;$('#qcss').textContent=CSS;$('#doc').innerHTML=d.body;$('#doc').querySelectorAll('.pg').forEach(p=>p.setAttribute('contenteditable','true'));
 $('#s_name').value=d.opts.name||'';$('#s_disc').value=d.opts.discount||0;$('#s_vat').value=d.opts.vat??18;$('#s_valid').value=d.opts.valid_days||30}
async function go(q){const r=await fetch(API+'/quote_doc'+(q||''));if(!r.ok){alert('שגיאה בטעינת ההצעה');return}load(await r.json())}
function dirty(){$('#sv').textContent='· שומר...';clearTimeout(tm);tm=setTimeout(async()=>{
 await fetch(API+'/quote_doc',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({body:body()})});$('#sv').textContent='· נשמר'},900)}
document.addEventListener('input',e=>{if(e.target.closest&&e.target.closest('#doc'))dirty()});
async function refresh(){if(!confirm('לבנות מחדש מנתוני כתב הכמויות? טקסטים שערכת ידנית יאבדו.'))return;await go('?refresh=1')}
async function reset(){return refresh()}
function st(){const s=$('#stp');s.hidden=!s.hidden}
async function saveSt(){let logo=null;const f=$('#s_logo').files[0];if(f)logo=await new Promise(r=>{const x=new FileReader();x.onload=()=>r(x.result);x.readAsDataURL(f)});
 await fetch(API+'/quote_opts',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:$('#s_name').value,discount:+$('#s_disc').value||0,vat:+$('#s_vat').value,valid_days:+$('#s_valid').value||30,logo})});
 st();await go('?refresh=1')}
async function exp(k){$('#sv').textContent='· מכין קובץ...';const r=await fetch(API+'/quote_doc.'+k,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({body:body()})});
 if(!r.ok){alert('הייצוא נכשל');$('#sv').textContent='· נשמר';return}const b=await r.blob(),a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='quote.'+k;a.click();$('#sv').textContent='· נשמר'}
go();
'''
def page(pid):
    return ('<!doctype html><html lang="he" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>עורך הצעת מחיר</title>'
            '<style id="qcss"></style><style>'+EXTRA_CSS+'</style><body>'+TOOLBAR+'<div id="doc"></div><script>'+JS.replace('%PID%',pid)+'</script></body></html>')
