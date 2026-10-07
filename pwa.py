"""Marathi PWA front-end served by FastAPI: /app, /manifest.webmanifest, /sw.js, /icon-192.png, /icon-512.png."""
from __future__ import annotations

import json
import struct
import zlib
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import HTMLResponse

router = APIRouter()

MANIFEST = {
    "name": "TenderBot AI — कंत्राटदाराचा डिजिटल मॅनेजर",
    "short_name": "TenderBot",
    "description": "टेंडर शोध, बिड रेट, सबमिशन मंजुरी, कागदपत्र व्हॉल्ट आणि GST सल्ला",
    "lang": "mr",
    "start_url": "/app",
    "scope": "/",
    "display": "standalone",
    "orientation": "portrait",
    "background_color": "#0d3b66",
    "theme_color": "#0d3b66",
    "icons": [
        {"src": "/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
        {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
    ],
}

SW_JS = """const CACHE='tenderbot-shell-v1';
self.addEventListener('install',e=>{e.waitUntil(caches.open(CACHE).then(c=>c.addAll(['/app'])));self.skipWaiting();});
self.addEventListener('activate',e=>{e.waitUntil(caches.keys().then(ks=>Promise.all(ks.filter(k=>k!==CACHE).map(k=>caches.delete(k)))));self.clients.claim();});
self.addEventListener('fetch',e=>{
  const u=new URL(e.request.url);
  if(e.request.method!=='GET'||u.pathname!=='/app')return;
  e.respondWith(fetch(e.request).then(r=>{const c=r.clone();caches.open(CACHE).then(x=>x.put('/app',c));return r;}).catch(()=>caches.match('/app')));
});
"""


@lru_cache(maxsize=4)
def _icon(size: int) -> bytes:
    bg, fg, accent = (13, 59, 102), (255, 255, 255), (244, 162, 89)
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        v = y / size
        for x in range(size):
            u = x / size
            if 0.26 <= u <= 0.74 and 0.28 <= v <= 0.40:
                color = fg
            elif 0.44 <= u <= 0.56 and 0.40 < v <= 0.72:
                color = fg
            elif 0.30 <= u <= 0.70 and 0.76 <= v <= 0.80:
                color = accent
            else:
                color = bg
            raw += bytes(color)

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9)) + chunk(b"IEND", b""))


@router.get("/manifest.webmanifest", include_in_schema=False)
def manifest() -> Response:
    return Response(json.dumps(MANIFEST, ensure_ascii=False), media_type="application/manifest+json")


@router.get("/sw.js", include_in_schema=False)
def service_worker() -> Response:
    return Response(SW_JS, media_type="application/javascript", headers={"Cache-Control": "no-cache"})


@router.get("/icon-{size}.png", include_in_schema=False)
def icon(size: int) -> Response:
    if size not in (192, 512):
        raise HTTPException(404)
    return Response(_icon(size), media_type="image/png", headers={"Cache-Control": "public, max-age=604800"})


@router.get("/app", response_class=HTMLResponse, include_in_schema=False)
def app_page() -> HTMLResponse:
    return HTMLResponse(APP_HTML, headers={"Cache-Control": "no-cache"})


APP_HTML = r"""<!DOCTYPE html>
<html lang="mr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0d3b66">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" href="/icon-192.png"><link rel="apple-touch-icon" href="/icon-192.png">
<title>TenderBot AI</title>
<style>
:root{--p:#0d3b66;--a:#f4a259;--bg:#f2f5fa;--c:#fff;--t:#1b2430;--m:#64748b;--ok:#15803d;--bad:#b91c1c;--warn:#b45309;--line:#e2e8f0}
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,"Noto Sans Devanagari",Roboto,sans-serif;background:var(--bg);color:var(--t);padding-top:env(safe-area-inset-top);padding-bottom:calc(68px + env(safe-area-inset-bottom));font-size:16px}
header{position:sticky;top:0;z-index:5;background:var(--p);color:#fff;display:flex;align-items:center;justify-content:space-between;padding:10px 14px}
header b{font-size:18px}.badge{background:var(--a);color:#1b2430;border-radius:99px;padding:3px 10px;font-size:12px;font-weight:700;margin-left:8px}
header button{background:none;border:0;color:#fff;font-size:22px}
main{padding:12px;max-width:640px;margin:auto}
.screen{display:none}.screen.on{display:block}
.card{background:var(--c);border-radius:14px;padding:14px;margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
h2{margin:0 0 8px;font-size:18px}h3{margin:12px 0 6px;font-size:15px}
label{display:block;font-size:13px;color:var(--m);margin:10px 0 4px}
input,select,textarea{width:100%;padding:11px;border:1px solid #cbd5e1;border-radius:10px;font-size:16px;background:#fff;font-family:inherit}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.btn{width:100%;margin-top:14px;padding:13px;border:0;border-radius:10px;background:var(--p);color:#fff;font-size:16px;font-weight:700}
.btn.sec{background:#e8eef7;color:var(--p)}.btn.ok{background:var(--ok)}.btn.bad{background:var(--bad)}.btn.sm{width:auto;margin:6px 6px 0 0;padding:8px 12px;font-size:14px}
.btn:disabled{opacity:.6}
nav{position:fixed;bottom:0;left:0;right:0;display:flex;background:#fff;border-top:1px solid var(--line);padding-bottom:env(safe-area-inset-bottom);z-index:6}
nav button{flex:1;border:0;background:none;padding:8px 2px;font-size:11px;color:var(--m)}
nav button span{display:block;font-size:22px}nav button.on{color:var(--p);font-weight:700}
.chip{display:inline-block;padding:2px 9px;border-radius:99px;font-size:12px;font-weight:700;background:#e2e8f0}
.chip.ok{background:#dcfce7;color:var(--ok)}.chip.bad{background:#fee2e2;color:var(--bad)}.chip.warn{background:#fef3c7;color:var(--warn)}
.muted{color:var(--m);font-size:13px}.err{background:#fee2e2;color:#7f1d1d;border-radius:10px;padding:12px;margin-top:10px}
.pay{background:#fff7ed;color:#9a3412;border:1px solid #fdba74;border-radius:10px;padding:12px;margin-top:10px;font-weight:600}
.info{background:#eff6ff;color:#1e3a8a;border-radius:10px;padding:10px;margin-top:10px;font-size:14px}
table{width:100%;border-collapse:collapse;font-size:14px}td{padding:6px 4px;border-bottom:1px solid var(--line)}td:last-child{text-align:right;white-space:nowrap}
.kpi{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:8px 0}.kpi div{background:#f1f5f9;border-radius:10px;padding:10px}.kpi small{color:var(--m);display:block}.kpi b{font-size:17px}
summary{font-weight:700;cursor:pointer}details>summary{margin-bottom:6px}
.row{display:flex;gap:8px;align-items:center}.row input[type=checkbox]{width:auto}
dialog{border:0;border-radius:16px;padding:16px;width:min(94vw,560px);max-height:88vh;overflow:auto}
dialog::backdrop{background:rgba(0,0,0,.5)}
#toast{position:fixed;left:12px;right:12px;bottom:84px;background:#1b2430;color:#fff;padding:12px;border-radius:10px;display:none;z-index:20;text-align:center}
.pr{border:1px dashed #cbd5e1;border-radius:10px;padding:8px;margin-top:8px}
</style></head><body>
<header><div><b>🏗️ TenderBot AI</b><span class="badge" id="planBadge">—</span></div><button onclick="show('profile')" aria-label="प्रोफाइल">👤</button></header>
<main>

<section id="s-search" class="screen">
 <div class="card"><h2>🔍 टेंडर शोध</h2>
  <label>कीवर्ड</label><input id="sf_q" placeholder="उदा. रस्ता, पूल, पाणीपुरवठा">
  <div class="grid2"><div><label>श्रेणी</label><input id="sf_category" list="cats" placeholder="civil"></div><div><label>जिल्हा</label><input id="sf_district" placeholder="पुणे"></div></div>
  <label>विभाग</label><input id="sf_department" placeholder="PWD, जिल्हा परिषद…">
  <div class="grid2"><div><label>किमान किंमत (₹)</label><input id="sf_min_cost" type="number" inputmode="numeric"></div><div><label>कमाल किंमत (₹)</label><input id="sf_max_cost" type="number" inputmode="numeric"></div></div>
  <button class="btn" onclick="doSearch()">शोधा</button></div>
 <div id="searchRes"></div>
 <details class="card"><summary>➕ नवीन टेंडर जोडा</summary>
  <label>टेंडर क्रमांक</label><input id="at_id"><label>कामाचे नाव</label><input id="at_title"><label>विभाग</label><input id="at_dept">
  <div class="grid2"><div><label>श्रेणी</label><input id="at_cat" list="cats"></div><div><label>जिल्हा</label><input id="at_dist"></div></div>
  <div class="grid2"><div><label>अंदाजित किंमत (₹)</label><input id="at_cost" type="number" inputmode="decimal"></div><div><label>EMD (₹)</label><input id="at_emd" type="number" inputmode="decimal"></div></div>
  <button class="btn sec" onclick="addTender()">टेंडर सेव्ह करा</button></details>
 <details class="card"><summary>🌐 पोर्टल लिंकवरून आणा</summary>
  <p class="muted">फक्त mahatenders.gov.in / eprocure.gov.in चे सार्वजनिक यादी-पेज चालते.</p>
  <label>पेज लिंक</label><input id="im_url" type="url"><div class="grid2"><div><label>श्रेणी</label><input id="im_cat" list="cats"></div><div><label>जिल्हा</label><input id="im_dist"></div></div>
  <button class="btn sec" onclick="importTenders()">आणा</button><div id="imRes"></div></details>
</section>

<section id="s-predict" class="screen">
 <div class="card"><h2>📈 बिड रेट प्रेडिक्शन</h2>
  <p class="muted">फक्त Mahatenders/CPPP च्या जुन्या अवार्ड डेटावरून. डेटा नसेल तर "जुना डेटा उपलब्ध नाही" येईल.</p>
  <label>श्रेणी</label><input id="pr_cat" list="cats" placeholder="civil">
  <label>विभाग</label><input id="pr_dept" placeholder="PWD">
  <label>कामाचे नाव (ऐच्छिक)</label><input id="pr_title">
  <div class="grid2"><div><label>अंदाजित किंमत (₹)</label><input id="pr_est" type="number" inputmode="decimal"></div><div><label>माझा खर्च अंदाज (₹)</label><input id="pr_own" type="number" inputmode="decimal"></div></div>
  <button class="btn" onclick="runPredict()">रेट सुचवा</button></div>
 <div id="predRes"></div>
</section>

<section id="s-approval" class="screen">
 <div class="card"><h2>✅ सबमिशन अप्रूव्हल</h2>
  <p class="muted">तुमच्या मंजुरीशिवाय काहीही सबमिट होत नाही. WhatsApp आणि मराठी कॉलवरही विचारले जाते.</p>
  <label>टेंडर क्रमांक</label><input id="ap_id"><label>कामाचे नाव</label><input id="ap_title">
  <label>बिड रक्कम (₹)</label><input id="ap_amt" type="number" inputmode="decimal">
  <div class="row" style="margin-top:10px"><input type="checkbox" id="ap_call" checked><span>मराठी व्हॉइस कॉलही करा</span></div>
  <button class="btn" onclick="reqApproval()">मंजुरी मागवा</button><div id="apRes"></div></div>
 <h3>माझी सबमिशन्स</h3><div id="subList"></div>
</section>

<section id="s-vault" class="screen">
 <div class="card"><h2>🗂️ डॉक्युमेंट व्हॉल्ट</h2><div id="vaultList"><p class="muted">लोड होत आहे…</p></div></div>
 <div class="card"><h3>कागदपत्र जोडा</h3>
  <label>प्रकार</label><select id="vd_type">
   <option value="GST Registration">GST नोंदणी</option><option value="PAN Card">PAN कार्ड</option><option value="PWD Registration">PWD नोंदणी</option>
   <option value="Class-1 Certificate">Class-1 प्रमाणपत्र</option><option value="EPF Certificate">EPF</option><option value="ESIC Certificate">ESIC</option>
   <option value="Labour Licence">कामगार परवाना</option><option value="Solvency Certificate">सॉल्व्हन्सी प्रमाणपत्र</option><option value="Turnover Certificate">उलाढाल प्रमाणपत्र</option>
   <option value="ITR">आयकर रिटर्न (ITR)</option><option value="Udyam Registration">उद्योग आधार / Udyam</option><option value="DSC">डिजिटल सही (DSC)</option></select>
  <label>किंवा दुसरा प्रकार लिहा</label><input id="vd_other">
  <label>क्रमांक</label><input id="vd_num"><label>मुदत संपण्याची तारीख</label><input id="vd_exp" type="date">
  <label>फाइल/ड्राइव्ह लिंक (ऐच्छिक)</label><input id="vd_ref" type="url">
  <button class="btn" onclick="addDoc()">जोडा</button></div>
</section>

<section id="s-gst" class="screen">
 <div class="card"><h2>🧾 GST सल्ला</h2>
  <label>करपात्र मूल्य (₹)</label><input id="g_val" type="number" inputmode="decimal">
  <div class="grid2"><div><label>GST दर (%)</label><input id="g_rate" type="number" value="18" inputmode="decimal"></div>
  <div><label>पुरवठा</label><select id="g_intra"><option value="1">राज्यांतर्गत (CGST+SGST)</option><option value="0">आंतरराज्य (IGST)</option></select></div></div>
  <div class="row" style="margin-top:10px"><input type="checkbox" id="g_tds"><span>सरकारी विभाग GST TDS कापतो</span></div>
  <h3>खरेदी (ITC साठी)</h3><div id="g_purch"></div>
  <button class="btn sec" onclick="addPurchase()">+ खरेदी जोडा</button>
  <button class="btn" onclick="runGst()">हिशोब करा</button></div>
 <div id="gstRes"></div>
</section>

<section id="s-profile" class="screen">
 <div class="card"><h2>👤 माझे प्रोफाइल</h2>
  <label>WhatsApp नंबर (+91…)</label><input id="pf_phone" type="tel" placeholder="+919876543210">
  <label>फर्मचे / तुमचे नाव</label><input id="pf_name">
  <div class="grid2"><div><label>वर्ग</label><input id="pf_class" placeholder="Class 1"></div><div><label>वार्षिक उलाढाल (₹)</label><input id="pf_turn" type="number" inputmode="decimal"></div></div>
  <label>श्रेणी (स्वल्पविरामाने)</label><input id="pf_cats" placeholder="civil, road"><label>जिल्हे (स्वल्पविरामाने)</label><input id="pf_dists" placeholder="पुणे, सातारा">
  <button class="btn" onclick="saveProfile()">सेव्ह करा</button>
  <button class="btn sec" id="installBtn" style="display:none" onclick="installApp()">📲 ॲप इन्स्टॉल करा</button>
  <div id="pfRes"></div></div>
</section>
</main>

<nav>
 <button data-s="search" onclick="show('search')"><span>🔍</span>शोध</button>
 <button data-s="predict" onclick="show('predict')"><span>📈</span>बिड रेट</button>
 <button data-s="approval" onclick="show('approval')"><span>✅</span>मंजुरी</button>
 <button data-s="vault" onclick="show('vault')"><span>🗂️</span>व्हॉल्ट</button>
 <button data-s="gst" onclick="show('gst')"><span>🧾</span>GST</button>
</nav>
<datalist id="cats"><option>civil</option><option>road</option><option>building</option><option>water supply</option><option>electrical</option><option>sand</option><option>material supply</option><option>labour</option></datalist>
<div id="toast"></div><dialog id="dlg"></dialog>

<script>
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const inr=n=>n==null?'—':'₹'+Number(n).toLocaleString('en-IN',{maximumFractionDigits:2});
const num=id=>{const v=$('#'+id).value.trim();return v===''?null:Number(v)};
const val=id=>$('#'+id).value.trim();
let phone=localStorage.getItem('tb_phone')||'';
let profile=JSON.parse(localStorage.getItem('tb_profile')||'{}');
let vaultDocs=[], lastTenders=[], deferredInstall=null;

function toast(m){const t=$('#toast');t.textContent=m;t.style.display='block';clearTimeout(toast.h);toast.h=setTimeout(()=>t.style.display='none',3500)}
function setPlan(d){const s=d.plan_status;$('#planBadge').textContent=s==='trial'?`ट्रायल: दिवस ${d.trial_day}/${d.trial_days_total||15}`:s==='expired'?'ट्रायल संपली':s==='vip'?'VIP':s==='basic'?'Basic':'—'}
async function api(path,method='GET',body){
  let r;try{r=await fetch(path,{method,headers:{'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined})}
  catch(e){throw new Error('सर्व्हरशी संपर्क होत नाही. इंटरनेट तपासा; सर्व्हर झोपला असल्यास १ मिनिट थांबून पुन्हा करा.')}
  let d=null;try{d=await r.json()}catch(e){}
  if(!r.ok){const det=d&&d.detail;
    if(r.status===402&&det&&det.message_mr){if(det.plan_status)setPlan(det);const e=new Error(det.message_mr);e.paywall=true;throw e}
    if(r.status===422&&Array.isArray(det))throw new Error('कृपया माहिती तपासा: '+det.map(x=>((x.loc||[]).slice(-1)[0]||'')+' — '+x.msg).join('; '));
    throw new Error(typeof det==='string'?det:(det&&det.message_mr)||('त्रुटी ('+r.status+')'))}
  if(d&&d.plan_status)setPlan(d);return d}
function fail(id,e){$('#'+id).innerHTML=`<div class="${e.paywall?'pay':'err'}">${esc(e.message)}</div>`}
function needPhone(){if(phone)return true;toast('आधी प्रोफाइलमध्ये तुमचा WhatsApp नंबर टाका');show('profile');return false}
async function busy(btn,fn){if(btn)btn.disabled=true;try{await fn()}finally{if(btn)btn.disabled=false}}

function show(id){
  document.querySelectorAll('.screen').forEach(s=>s.classList.toggle('on',s.id==='s-'+id));
  document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('on',b.dataset.s===id));
  window.scrollTo(0,0);
  if(id==='approval'&&phone)loadSubs();
  if(id==='vault'&&phone)loadVault();
  if(id==='search'&&!lastTenders.length)doSearch(true);
}

/* ---------- 1. Tender search ---------- */
async function doSearch(silent){
  const p=new URLSearchParams();
  [['q','sf_q'],['category','sf_category'],['district','sf_district'],['department','sf_department'],['min_cost','sf_min_cost'],['max_cost','sf_max_cost']].forEach(([k,i])=>{const v=val(i);if(v)p.set(k,v)});
  try{const d=await api('/tenders/search?'+p);lastTenders=d.tenders;
    $('#searchRes').innerHTML=d.tenders.length?`<p class="muted">${d.count} टेंडर सापडले</p>`+d.tenders.map((t,i)=>`<div class="card"><b>${esc(t.title)}</b>
      <div class="muted">${esc(t.tender_id)} · ${esc(t.department)}</div>
      <div class="kpi"><div><small>अंदाजित किंमत</small><b>${inr(t.estimated_cost)}</b></div><div><small>EMD</small><b>${inr(t.emd_amount)}</b></div></div>
      <span class="chip">${esc(t.category)}</span> ${t.district?`<span class="chip">${esc(t.district)}</span>`:''}
      <div><button class="btn sm sec" onclick="toPredict(${i})">📈 बिड रेट</button><button class="btn sm sec" onclick="openAnalyze(${i})">📋 पात्रता तपासा</button><button class="btn sm" onclick="toApproval(${i})">✅ मंजुरी</button></div></div>`).join('')
      :'<div class="info">या फिल्टरने कोणतेही टेंडर नाही. खाली "नवीन टेंडर जोडा" वापरून पोर्टलवरचे टेंडर जोडा.</div>'}
  catch(e){if(!silent)fail('searchRes',e)}}
async function addTender(){if(!needPhone())return;
  try{await api('/tenders','POST',{phone,tender_id:val('at_id'),title:val('at_title'),department:val('at_dept'),category:val('at_cat')||'general',district:val('at_dist')||null,estimated_cost:num('at_cost'),emd_amount:num('at_emd')});
    toast('टेंडर सेव्ह झाले');['at_id','at_title','at_dept','at_cat','at_dist','at_cost','at_emd'].forEach(i=>$('#'+i).value='');doSearch()}catch(e){toast(e.message)}}
async function importTenders(){
  try{const d=await api('/discover-tenders','POST',{url:val('im_url'),category:val('im_cat')||null,district:val('im_dist')||null,save:true});
    $('#imRes').innerHTML=`<div class="info">${d.count} ओळी सापडल्या, ${d.saved} नवीन सेव्ह झाल्या.</div>`;doSearch()}catch(e){fail('imRes',e)}}
function toPredict(i){const t=lastTenders[i];$('#pr_cat').value=t.category;$('#pr_dept').value=t.department;$('#pr_title').value=t.title;$('#pr_est').value=t.estimated_cost;show('predict')}
function toApproval(i){const t=lastTenders[i];$('#ap_id').value=t.tender_id;$('#ap_title').value=t.title;$('#ap_amt').value='';show('approval')}
async function openAnalyze(i){
  if(!needPhone())return;const t=lastTenders[i];await loadVault(true);
  const d=$('#dlg');d.innerHTML=`<h2>📋 पात्रता तपासणी</h2><p class="muted">${esc(t.title)}</p>
   <label>निविदेत मागितलेली कागदपत्रे (प्रत्येक वेगळ्या ओळीत)</label><textarea id="an_docs" rows="5" placeholder="GST Registration&#10;PAN Card&#10;EPF Certificate"></textarea>
   <div class="grid2"><div><label>किमान वर्ग</label><input id="an_class" placeholder="Class 1"></div><div><label>किमान उलाढाल (₹)</label><input id="an_turn" type="number"></div></div>
   <p class="muted">तुमच्याकडे असलेली कागदपत्रे व्हॉल्टमधून घेतली जातात (${vaultDocs.length}).</p>
   <button class="btn" id="an_go">तपासा</button><button class="btn sec" onclick="$('#dlg').close()">बंद करा</button><div id="anRes"></div>`;
  d.showModal();
  $('#an_go').onclick=()=>busy($('#an_go'),async()=>{
    const docs=val('an_docs').split('\n').map(s=>s.trim()).filter(Boolean);
    if(!docs.length){$('#anRes').innerHTML='<div class="err">किमान एक कागदपत्र लिहा.</div>';return}
    try{const r=await api('/analyze-tender','POST',{vendor:{phone,name:profile.name||'कंत्राटदार',contractor_class:profile.contractor_class||null,categories:profile.categories||[],districts:profile.districts||[],annual_turnover:profile.annual_turnover??null,documents_held:vaultDocs.map(x=>x.doc_type)},
      tender:{tender_id:t.tender_id,title:t.title,department:t.department,category:t.category,district:t.district,estimated_cost:t.estimated_cost,emd_amount:t.emd_amount,required_documents:docs,minimum_class:val('an_class')||null,min_turnover:num('an_turn')},send_whatsapp:false});
      const a=r.analysis,v=a.eligible===true?['पात्र','ok']:a.eligible===false?['अपात्र / त्रुटी','bad']:['तपासणी अपूर्ण','warn'];
      $('#anRes').innerHTML=`<div class="card"><span class="chip ${v[1]}">${v[0]}</span>
       ${a.missing_documents.length?`<h3>❌ कमी कागदपत्रे</h3><ul>${a.missing_documents.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
       ${a.matched_documents.length?`<h3>✅ उपलब्ध</h3><ul>${a.matched_documents.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
       ${a.issues.concat(a.unverified).map(x=>`<p>⚠️ ${esc(x)}</p>`).join('')}</div>`}
    catch(e){fail('anRes',e)}})}

/* ---------- 2. Bid rate predictor ---------- */
async function runPredict(){if(!needPhone())return;
  const est=num('pr_est');if(!val('pr_cat')||!est){$('#predRes').innerHTML='<div class="err">श्रेणी आणि अंदाजित किंमत आवश्यक आहे.</div>';return}
  try{const d=await api('/predict-bid-rate','POST',{phone,tender:{tender_id:'ADHOC',title:val('pr_title')||'बिड रेट चाचणी',department:val('pr_dept')||'—',category:val('pr_cat'),estimated_cost:est},own_cost_estimate:num('pr_own')});
    const p=d.prediction;
    if(!p.data_available){$('#predRes').innerHTML=`<div class="card"><h2>${esc(p.message_mr)}</h2><p class="muted">सापडलेले नमुने: ${p.samples_found} (किमान ${p.minimum_samples_required} हवेत). Admin ने अवार्ड डेटा भरला की येथे अंदाज दिसेल.</p></div>`;return}
    const L={aggressive:'आक्रमक (जिंकण्याची शक्यता जास्त)',recommended:'सुचवलेला (अंदाजे L1)',conservative:'सावध (नफा जास्त)'};
    $('#predRes').innerHTML=`<div class="card"><h2>${esc(p.predicted_l1_description_mr)}</h2><p>${esc(p.narrative_mr)}</p>
      ${Object.entries(p.scenarios).map(([k,s])=>`<div class="pr"><b>${L[k]}</b><div class="kpi"><div><small>रेट</small><b>${s.percent_vs_estimate>0?'+':''}${s.percent_vs_estimate}%</b></div><div><small>बिड रक्कम</small><b>${inr(s.bid_amount)}</b></div>
      ${s.profit_margin_percent!=null?`<div><small>नफा</small><b>${inr(s.profit_amount)}</b></div><div><small>मार्जिन</small><b>${s.profit_margin_percent}%</b></div>`:''}</div></div>`).join('')}
      ${p.warnings_mr.map(w=>`<div class="err">${esc(w)}</div>`).join('')}
      <p class="muted">आधार: ${p.data_basis.samples} अवार्ड्स · ${esc(p.data_basis.sources.join(', '))} · ${esc(p.data_basis.match_scope)}</p>
      ${p.frequent_winners.length?`<h3>वारंवार जिंकणारे</h3>${p.frequent_winners.map(w=>`<div>${esc(w.name)} — ${w.wins}</div>`).join('')}`:''}</div>`}
  catch(e){fail('predRes',e)}}

/* ---------- 3. Submission approval ---------- */
const ST={PENDING:['मंजुरी प्रलंबित','warn'],CANCELLED:['रद्द','bad'],APPROVED_AWAITING_PORTAL_SUBMISSION:['मंजूर — पोर्टल सबमिशन बाकी','warn'],SUBMITTED:['सबमिट झाले','ok'],APPROVED_SUBMISSION_FAILED:['सबमिशन अयशस्वी','bad']};
async function reqApproval(){if(!needPhone())return;
  try{const d=await api('/request-submit-approval','POST',{phone,tender_id:val('ap_id'),tender_title:val('ap_title'),bid_amount:num('ap_amt'),place_call:$('#ap_call').checked});
    const dry=(d.whatsapp&&d.whatsapp.mode==='dry_run')?'<br>⚠️ Twilio जोडलेले नाही — WhatsApp/कॉल पाठवला गेला नाही. खाली ॲपमध्येच मंजुरी द्या.':'';
    $('#apRes').innerHTML=`<div class="info">${esc(d.prompt_mr)}${dry}</div>`;loadSubs()}catch(e){fail('apRes',e)}}
async function loadSubs(){
  try{const d=await api('/submissions?phone='+encodeURIComponent(phone));
    $('#subList').innerHTML=d.submissions.length?d.submissions.map(s=>{const st=ST[s.status]||[s.status,''];
      return `<div class="card"><b>${esc(s.tender_title)}</b><div class="muted">${esc(s.tender_ref)} · ${inr(s.bid_amount)}</div><span class="chip ${st[1]}">${st[0]}</span>
      ${s.detail?`<p class="muted">${esc(s.detail)}</p>`:''}
      ${s.status==='PENDING'?`<button class="btn sm ok" onclick="decide(${s.id},'YES')">होय, सबमिट करा</button><button class="btn sm bad" onclick="decide(${s.id},'NO')">नाही, रद्द करा</button>`:''}</div>`}).join(''):'<div class="info">अजून कोणतेही सबमिशन नाही.</div>'}
  catch(e){fail('subList',e)}}
async function decide(id,decision){
  if(!confirm(decision==='YES'?'खात्री आहे? बिड मंजूर होईल.':'हे सबमिशन रद्द करायचे?'))return;
  try{const r=await api(`/submissions/${id}/decision`,'POST',{phone,decision});toast(r.message_mr);loadSubs()}catch(e){toast(e.message)}}

/* ---------- 4. Document vault ---------- */
const VS={valid:['वैध','ok'],expiring_soon:['लवकरच संपणार','warn'],expired:['संपले','bad'],no_expiry:['मुदत नाही','']};
async function loadVault(silent){
  try{const d=await api('/vault/documents?phone='+encodeURIComponent(phone));vaultDocs=d.documents;
    if(silent)return;
    $('#vaultList').innerHTML=d.documents.length?d.documents.map(x=>{const s=VS[x.status]||[x.status,''];
      return `<div class="pr"><b>${esc(x.doc_type)}</b> <span class="chip ${s[1]}">${s[0]}</span><div class="muted">${x.doc_number?'क्र. '+esc(x.doc_number)+' · ':''}${x.expiry_date?'मुदत: '+esc(x.expiry_date)+(x.days_left!=null?` (${x.days_left} दिवस)`:''):''}</div>
      ${x.file_ref?`<a href="${esc(x.file_ref)}" target="_blank" rel="noopener">फाइल उघडा</a>`:''}</div>`}).join(''):'<div class="info">व्हॉल्ट रिकामा आहे. खाली कागदपत्र जोडा. मुदत संपण्याच्या ३० दिवस आधी WhatsApp अलर्ट येतो.</div>'}
  catch(e){if(!silent)fail('vaultList',e)}}
async function addDoc(){if(!needPhone())return;
  try{await api('/vault/documents','POST',{phone,doc_type:val('vd_other')||val('vd_type'),doc_number:val('vd_num')||null,expiry_date:val('vd_exp')||null,file_ref:val('vd_ref')||null});
    toast('कागदपत्र जोडले');['vd_other','vd_num','vd_exp','vd_ref'].forEach(i=>$('#'+i).value='');loadVault()}catch(e){toast(e.message)}}

/* ---------- 5. GST advice ---------- */
function addPurchase(){const d=document.createElement('div');d.className='pr';
  d.innerHTML=`<input class="pd" placeholder="खरेदीचे नाव (उदा. सिमेंट)"><div class="grid2"><div><label>मूल्य (₹)</label><input class="pv" type="number" inputmode="decimal"></div><div><label>GST %</label><input class="pg" type="number" value="18" inputmode="decimal"></div></div>
  <div class="row" style="margin-top:8px"><input type="checkbox" class="pe" checked><span>ITC पात्र</span><button class="btn sm sec" style="margin:0 0 0 auto" onclick="this.closest('.pr').remove()">काढा</button></div>`;$('#g_purch').appendChild(d)}
async function runGst(){if(!needPhone())return;
  const purchases=[...document.querySelectorAll('#g_purch .pr')].map(r=>({description:r.querySelector('.pd').value.trim()||'खरेदी',taxable_value:Number(r.querySelector('.pv').value||0),gst_rate_percent:Number(r.querySelector('.pg').value||0),itc_eligible:r.querySelector('.pe').checked})).filter(p=>p.taxable_value>0);
  try{const d=await api('/get-tax-advice','POST',{phone,taxable_value:num('g_val'),gst_rate_percent:num('g_rate'),intra_state:val('g_intra')==='1',purchases,gst_tds_applicable:$('#g_tds').checked});
    const rows=d.ca_ready_breakdown;
    $('#gstRes').innerHTML=`<div class="card"><h2>निकाल</h2><p>${esc(d.summary_mr)}</p>
     <div class="kpi"><div><small>आउटपुट GST</small><b>${inr(d.output_tax.total)}</b></div><div><small>पात्र ITC</small><b>${inr(d.itc.eligible_total)}</b></div><div><small>निव्वळ GST देय</small><b>${inr(d.net_gst_payable)}</b></div><div><small>मिळणारी रक्कम</small><b>${inr(d.expected_receipt)}</b></div></div>
     ${rows?`<h3>सीए-रेडी तपशील</h3><table>${rows.map(r=>`<tr><td>${esc(r.particular)}</td><td>${inr(r.amount)}</td></tr>`).join('')}</table>
       <button class="btn sec" onclick='shareGst(${JSON.stringify(JSON.stringify(rows))})'>📤 सीए ला शेअर करा</button>`
       :`<div class="pay">${esc((d.ca_ready_export||{}).message_mr||'फक्त ड्राफ्ट उपलब्ध')}</div>`}
     <h3>टॅक्स नियोजन सूचना</h3><ul>${d.strategies_mr.map(s=>`<li>${esc(s)}</li>`).join('')}</ul><p class="muted">${esc(d.disclaimer_mr)}</p></div>`}
  catch(e){fail('gstRes',e)}}
function shareGst(json){const rows=JSON.parse(json);const text='GST हिशोब (TenderBot AI)\n'+rows.map(r=>`${r.particular.trim()}: ${inr(r.amount)}`).join('\n');
  if(navigator.share)navigator.share({text}).catch(()=>{});else{navigator.clipboard.writeText(text);toast('कॉपी केले')}}

/* ---------- Profile ---------- */
function fillProfile(){$('#pf_phone').value=phone;$('#pf_name').value=profile.name||'';$('#pf_class').value=profile.contractor_class||'';$('#pf_turn').value=profile.annual_turnover??'';$('#pf_cats').value=(profile.categories||[]).join(', ');$('#pf_dists').value=(profile.districts||[]).join(', ')}
const list=s=>s.split(',').map(x=>x.trim()).filter(Boolean);
async function saveProfile(){
  const p=val('pf_phone');if(!p){$('#pfRes').innerHTML='<div class="err">नंबर आवश्यक आहे.</div>';return}
  try{const d=await api('/me','POST',{phone:p,name:val('pf_name')||null,contractor_class:val('pf_class')||null,annual_turnover:num('pf_turn'),categories:list(val('pf_cats')),districts:list(val('pf_dists'))});
    phone=d.phone;profile={name:d.name,contractor_class:d.contractor_class,annual_turnover:d.annual_turnover,categories:d.categories,districts:d.districts};
    localStorage.setItem('tb_phone',phone);localStorage.setItem('tb_profile',JSON.stringify(profile));
    $('#pfRes').innerHTML='<div class="info">प्रोफाइल सेव्ह झाले ✔</div>';toast('सेव्ह झाले')}catch(e){fail('pfRes',e)}}
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();deferredInstall=e;$('#installBtn').style.display='block'});
function installApp(){if(deferredInstall){deferredInstall.prompt();deferredInstall=null}}

/* ---------- start ---------- */
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
addPurchase();fillProfile();
if(phone){api('/me?phone='+encodeURIComponent(phone)).then(d=>{profile={name:d.name,contractor_class:d.contractor_class,annual_turnover:d.annual_turnover,categories:d.categories,districts:d.districts};localStorage.setItem('tb_profile',JSON.stringify(profile));fillProfile()}).catch(()=>{});show('search')}
else show('profile');
</script></body></html>
"""
