// Reads a DWG with libredwg (WASM) and writes a compact JSON of the geometry: model space + block definitions.
// usage: node dwg2json.mjs in.dwg out.json
import {Dwg_File_Type,LibreDwg} from '@mlightcad/libredwg-web';
import fs from 'fs'; import path from 'path'; import {fileURLToPath} from 'url';
const here=path.dirname(fileURLToPath(import.meta.url));
const lib=await LibreDwg.create(path.join(here,'node_modules/@mlightcad/libredwg-web/wasm/')+'/');
const buf=fs.readFileSync(process.argv[2]);
const dwg=lib.dwg_read_data(buf.buffer.slice(buf.byteOffset,buf.byteOffset+buf.byteLength),Dwg_File_Type.DWG);
if(!dwg){console.error('READ FAIL');process.exit(2)}
const db=lib.convert(dwg);
const p=(o)=>o?[o.x,o.y]:[0,0];
const clean=s=>String(s||'').replace(/\\P/g,'\n').replace(/\\[A-Za-z][^;]*;/g,'').replace(/[{}]/g,'').replace(/%%[cC]/g,'Ø').replace(/%%[dD]/g,'°').replace(/%%[pP]/g,'±');
function simp(e){
  const L=e.layer||'0',t=e.type;
  switch(t){
    case 'LINE':return {t:'L',l:L,a:p(e.startPoint),b:p(e.endPoint)};
    case 'LWPOLYLINE':return {t:'P',l:L,c:(e.flag&1)?1:0,v:(e.vertices||[]).map(v=>[v.x,v.y,v.bulge||0])};
    case 'POLYLINE2D':case 'POLYLINE_2D':case 'POLYLINE':return e.vertices?{t:'P',l:L,c:(e.flag&1)?1:0,v:e.vertices.map(v=>[v.x,v.y,v.bulge||0])}:null;
    case 'ARC':return {t:'A',l:L,c:p(e.center),r:e.radius,s:e.startAngle,e:e.endAngle};
    case 'CIRCLE':return {t:'C',l:L,c:p(e.center),r:e.radius};
    case 'ELLIPSE':return {t:'E',l:L,c:p(e.center),m:p(e.majorAxisEndPoint),q:e.axisRatio,s:e.startAngle,e:e.endAngle};
    case 'SPLINE':{const pts=(e.fitPoints&&e.fitPoints.length?e.fitPoints:e.controlPoints)||[];return pts.length>1?{t:'P',l:L,c:0,v:pts.map(v=>[v.x,v.y,0])}:null}
    case 'SOLID':case 'TRACE':{const c=[e.corner1,e.corner2,e.corner3,e.corner4].filter(Boolean);return c.length>2?{t:'S',l:L,v:c.map(p)}:null}
    case 'HATCH':{const out=[];for(const b of e.boundaryPaths||[]){if(b.vertices&&b.vertices.length>2)out.push({t:'P',l:L,c:1,v:b.vertices.map(v=>[v.x,v.y,v.bulge||0]),h:1})}return out.length?out:null}
    case 'TEXT':case 'ATTRIB':case 'ATTDEF':{const tx=clean(e.text);return tx?{t:'T',l:L,x:tx,p:p(e.startPoint),h:e.textHeight||0,r:e.rotation||0}:null}
    case 'MTEXT':{const tx=clean(e.text);return tx?{t:'T',l:L,x:tx,p:p(e.insertionPoint),h:e.textHeight||0,r:e.rotation||0}:null}
    case 'INSERT':return {t:'I',l:L,n:e.name,p:p(e.insertionPoint),sx:e.xScale??1,sy:e.yScale??1,r:e.rotation||0,nc:e.columnCount||1,nr:e.rowCount||1,dc:e.columnSpacing||0,dr:e.rowSpacing||0};
    case 'DIMENSION':return e.text?{t:'T',l:L,x:clean(e.text),p:p(e.textPoint),h:0,r:e.textRotation||0}:null;
    default:return null}}
const flat=(arr)=>{const o=[];for(const e of arr||[]){const s=simp(e);if(!s)continue;if(Array.isArray(s))o.push(...s);else o.push(s)}return o};
const model=flat(db.entities);
const blocks={};
for(const b of db.tables.BLOCK_RECORD.entries){if(/^\*(Model|Paper)/i.test(b.name))continue;const es=flat(b.entities);if(es.length)blocks[b.name]={base:p(b.basePoint),ents:es}}
const layers=(db.tables.LAYER.entries||[]).map(l=>({n:l.name,off:!!l.off,fr:!!l.frozen}));
fs.writeFileSync(process.argv[3],JSON.stringify({units:db.header?.INSUNITS??0,layers,blocks,model},(k,v)=>typeof v==='bigint'?Number(v):v));
console.log(JSON.stringify({model:model.length,blocks:Object.keys(blocks).length,layers:layers.length}));
