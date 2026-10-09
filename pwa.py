"""Marathi PWA front-end served by FastAPI: /app, /manifest.webmanifest, /sw.js, /icon-192.png, /icon-512.png."""
from __future__ import annotations

import json
import struct
import zlib
from functools import lru_cache

from fastapi import APIRouter, HTTPException, Response

from config import get_settings
from fastapi.responses import HTMLResponse

router = APIRouter()

MANIFEST = {
    "id": "/app",
    "name": "TenderBot AI — कंत्राटदाराचा डिजिटल मॅनेजर",
    "short_name": "TenderBot",
    "description": "टेंडर शोध, बिड रेट, सबमिशन मंजुरी, कागदपत्र व्हॉल्ट आणि GST सल्ला",
    "lang": "mr",
    "dir": "ltr",
    "categories": ["business", "productivity"],
    "prefer_related_applications": False,
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

SW_JS = """const CACHE='tenderbot-shell-v3';
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


@router.get("/.well-known/assetlinks.json", include_in_schema=False)
def asset_links() -> Response:
    """Digital Asset Links so the Android app (Trusted Web Activity) opens full-screen without the browser bar."""
    s = get_settings()
    fingerprints = [f.strip() for f in s.android_sha256_fingerprints.split(",") if f.strip()]
    data: list = []
    if s.android_package_name and fingerprints:
        data = [{"relation": ["delegate_permission/common.handle_all_urls"],
                 "target": {"namespace": "android_app", "package_name": s.android_package_name.strip(),
                            "sha256_cert_fingerprints": fingerprints}}]
    return Response(json.dumps(data), media_type="application/json", headers={"Cache-Control": "no-cache"})


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
<meta name="theme-color" content="#0b2a4a">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" href="/icon-192.png"><link rel="apple-touch-icon" href="/icon-192.png">
<title>TenderBot AI</title>
<style>
:root{--bg:#f2f5fb;--card:#fff;--text:#12202f;--muted:#66758b;--line:#e4e9f2;--p1:#0b2a4a;--p2:#1560a8;--acc:#ff9f1c;--ok:#16a34a;--bad:#dc2626;--warn:#d97706;--soft:#eef3fa;--shadow:0 6px 18px rgba(11,42,74,.08)}
@media(prefers-color-scheme:dark){:root{--bg:#0a1120;--card:#121b2d;--text:#e8eef8;--muted:#92a3bc;--line:#22314a;--soft:#18243a;--shadow:none}}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html{scroll-behavior:smooth}
body{margin:0;font-family:system-ui,"Noto Sans Devanagari",Roboto,sans-serif;background:var(--bg);color:var(--text);font-size:16px;line-height:1.45;padding-bottom:calc(88px + env(safe-area-inset-bottom))}
header{position:sticky;top:0;z-index:10;background:linear-gradient(135deg,var(--p1),var(--p2));color:#fff;padding:calc(10px + env(safe-area-inset-top)) 14px 12px;border-radius:0 0 22px 22px;box-shadow:0 8px 22px rgba(11,42,74,.25)}
.hrow{display:flex;align-items:center;justify-content:space-between;gap:8px}
.logo{display:flex;align-items:center;gap:8px;font-weight:800;font-size:19px;background:none;border:0;color:#fff;padding:0}
.logo i{font-style:normal;background:#fff;color:var(--p1);width:34px;height:34px;border-radius:11px;display:grid;place-items:center;font-size:20px}
.seg{display:flex;background:rgba(255,255,255,.18);border-radius:99px;padding:3px}
.seg button{border:0;background:none;color:#fff;padding:5px 11px;border-radius:99px;font-size:13px;font-weight:700}
.seg button.on{background:#fff;color:var(--p1)}
.avatar{border:0;background:rgba(255,255,255,.2);color:#fff;width:36px;height:36px;border-radius:50%;font-size:18px}
.badge{display:inline-block;margin-top:8px;background:var(--acc);color:#2a1700;border-radius:99px;padding:3px 11px;font-size:12px;font-weight:800}
main{padding:14px;max-width:640px;margin:auto}
.screen{display:none;animation:fade .25s}.screen.on{display:block}
@keyframes fade{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.title{display:flex;align-items:center;gap:10px;margin:2px 2px 12px}
.title .ic{width:42px;height:42px;border-radius:14px;background:var(--soft);display:grid;place-items:center;font-size:22px}
.title h2{margin:0;font-size:20px}.title p{margin:0;color:var(--muted);font-size:13px}
.card{background:var(--card);border-radius:18px;padding:15px;margin-bottom:14px;box-shadow:var(--shadow);border:1px solid var(--line)}
h3{margin:14px 0 6px;font-size:15px}
label{display:block;font-size:13px;font-weight:600;color:var(--muted);margin:12px 0 5px}
input,select,textarea{width:100%;padding:13px 12px;border:1.5px solid var(--line);border-radius:13px;font-size:16px;background:var(--card);color:var(--text);font-family:inherit;outline:none;transition:border .15s,box-shadow .15s}
input:focus,select:focus,textarea:focus{border-color:var(--p2);box-shadow:0 0 0 4px rgba(21,96,168,.15)}
.hint{font-size:12px;color:var(--p2);margin-top:4px;min-height:0;font-weight:600}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.btn{position:relative;width:100%;margin-top:16px;padding:14px;border:0;border-radius:14px;background:linear-gradient(135deg,var(--p1),var(--p2));color:#fff;font-size:16px;font-weight:800;box-shadow:0 6px 14px rgba(21,96,168,.28)}
.btn.sec{background:var(--soft);color:var(--p2);box-shadow:none}.btn.ok{background:var(--ok);box-shadow:none}.btn.bad{background:var(--bad);box-shadow:none}
.btn.sm{width:auto;margin:8px 8px 0 0;padding:9px 13px;font-size:14px;border-radius:11px}
.btn.loading{pointer-events:none;opacity:.75}.btn.loading::after{content:"";display:inline-block;width:14px;height:14px;margin-left:8px;border:2px solid #fff;border-top-color:transparent;border-radius:50%;vertical-align:-2px;animation:spin .7s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
nav{position:fixed;left:10px;right:10px;bottom:calc(10px + env(safe-area-inset-bottom));display:flex;background:var(--card);border:1px solid var(--line);border-radius:22px;padding:6px;box-shadow:0 10px 30px rgba(11,42,74,.22);z-index:12;max-width:620px;margin:auto}
nav button{flex:1;border:0;background:none;padding:6px 0;font-size:11px;font-weight:700;color:var(--muted);border-radius:16px}
nav button span{display:block;font-size:21px;line-height:1.2}nav button.on{background:var(--soft);color:var(--p2)}
body.anon nav,body.anon .avatar{display:none}
.tiles{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.tile{border:1px solid var(--line);background:var(--card);border-radius:18px;padding:14px;text-align:left;box-shadow:var(--shadow);color:var(--text)}
.tile .ic{width:44px;height:44px;border-radius:14px;display:grid;place-items:center;font-size:23px;margin-bottom:8px}
.tile b{display:block;font-size:15px}.tile small{color:var(--muted);font-size:12px}
.hero{background:linear-gradient(135deg,var(--p1),var(--p2));color:#fff;border-radius:20px;padding:18px;margin-bottom:14px;box-shadow:0 10px 24px rgba(11,42,74,.25)}
.hero h2{margin:0 0 4px;font-size:21px}.hero p{margin:0;opacity:.85;font-size:14px}
.bar{height:9px;background:rgba(255,255,255,.25);border-radius:9px;margin-top:12px;overflow:hidden}.bar i{display:block;height:100%;background:var(--acc);border-radius:9px;width:0}
.stats{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:12px;box-shadow:var(--shadow)}.stat b{font-size:26px;display:block}.stat small{color:var(--muted)}
.chip{display:inline-block;padding:3px 10px;border-radius:99px;font-size:12px;font-weight:700;background:var(--soft);color:var(--p2);margin:2px 4px 2px 0}
.chip.ok{background:rgba(22,163,74,.15);color:var(--ok)}.chip.bad{background:rgba(220,38,38,.14);color:var(--bad)}.chip.warn{background:rgba(217,119,6,.16);color:var(--warn)}
.muted{color:var(--muted);font-size:13px}
.err{background:rgba(220,38,38,.12);color:var(--bad);border-radius:13px;padding:12px;margin-top:12px;font-weight:600}
.pay{background:rgba(255,159,28,.15);color:var(--warn);border:1px solid rgba(255,159,28,.5);border-radius:13px;padding:12px;margin-top:12px;font-weight:700}
.info{background:var(--soft);color:var(--text);border-radius:13px;padding:12px;margin-top:12px;font-size:14px}
.empty{text-align:center;padding:26px 12px;color:var(--muted)}.empty .big{font-size:42px;display:block;margin-bottom:6px}
table{width:100%;border-collapse:collapse;font-size:14px}td{padding:8px 4px;border-bottom:1px solid var(--line)}td:last-child{text-align:right;white-space:nowrap;font-weight:700}
.kpi{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}.kpi div{background:var(--soft);border-radius:12px;padding:10px}.kpi small{color:var(--muted);display:block;font-size:12px}.kpi b{font-size:17px}
.big-rate{font-size:38px;font-weight:900;color:var(--p2);line-height:1.1}
.sc{border-left:5px solid var(--line);background:var(--soft);border-radius:12px;padding:10px 12px;margin-top:10px}.sc.rec{border-color:var(--ok)}.sc.agg{border-color:var(--warn)}.sc.con{border-color:var(--p2)}
summary{font-weight:800;cursor:pointer;padding:2px 0}
.row{display:flex;gap:10px;align-items:center}.row input[type=checkbox]{width:22px;height:22px;flex:none}
.sb{display:flex;gap:8px}.sb input{flex:1}.sb button{width:auto;margin:0;padding:0 18px}
dialog{border:0;border-radius:22px;padding:16px;width:min(94vw,560px);max-height:88vh;overflow:auto;background:var(--card);color:var(--text)}
dialog::backdrop{background:rgba(5,12,25,.6)}
#toast{position:fixed;left:14px;right:14px;bottom:calc(100px + env(safe-area-inset-bottom));background:#0b1a2e;color:#fff;padding:13px;border-radius:14px;display:none;z-index:30;text-align:center;font-weight:600}
.pr{border:1.5px dashed var(--line);border-radius:14px;padding:10px;margin-top:10px}
.langpick{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:8px 0}
.langpick button{border:2px solid var(--line);background:var(--card);color:var(--text);border-radius:14px;padding:14px;font-size:17px;font-weight:800}.langpick button.on{border-color:var(--p2);background:var(--soft);color:var(--p2)}
.bar2{height:9px;background:var(--soft);border-radius:9px;overflow:hidden;margin-top:8px}.bar2 i{display:block;height:100%;background:var(--ok);border-radius:9px;width:0;transition:width .4s}
#chatFab{position:fixed;right:14px;bottom:calc(98px + env(safe-area-inset-bottom));z-index:11;width:56px;height:56px;border-radius:50%;border:0;background:linear-gradient(135deg,var(--acc),#ff7a00);color:#fff;font-size:26px;box-shadow:0 10px 24px rgba(255,122,0,.4)}
body.anon #chatFab{display:none}
dialog.chat{padding:0;height:min(88vh,680px);overflow:hidden}
dialog.chat[open]{display:flex;flex-direction:column}
.chat .ch{display:flex;justify-content:space-between;align-items:center;padding:12px 14px;background:linear-gradient(135deg,var(--p1),var(--p2));color:#fff;font-weight:800}
.chat .ch button{background:none;border:0;color:#fff;font-size:22px}
#chatLog{flex:1;overflow:auto;padding:12px;display:flex;flex-direction:column;gap:8px}
.msg{max-width:86%;padding:10px 12px;border-radius:16px;font-size:15px;word-wrap:break-word}
.msg.bot{background:var(--soft);align-self:flex-start;border-bottom-left-radius:4px}
.msg.me{background:var(--p2);color:#fff;align-self:flex-end;border-bottom-right-radius:4px}
.chips{display:flex;gap:6px;flex-wrap:wrap;padding:0 12px 8px}.chips button{border:1px solid var(--line);background:var(--card);color:var(--p2);border-radius:99px;padding:6px 11px;font-size:13px;font-weight:700}
.chat .cin{display:flex;gap:8px;padding:10px;border-top:1px solid var(--line)}.chat .cin input{flex:1}.chat .cin button{width:50px;border:0;border-radius:13px;background:var(--p2);color:#fff;font-size:20px}
.row2{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 0;border-bottom:1px solid var(--line)}.row2:last-child{border-bottom:0}.row2 b{display:block}
.docacts{white-space:nowrap}.docacts button{border:0;background:var(--soft);color:var(--p2);border-radius:10px;padding:8px 10px;font-weight:700;font-size:14px;margin-left:4px}.docacts button.dng{color:var(--bad)}
</style></head><body class="anon">
<header>
 <div class="hrow">
  <button class="logo" onclick="go('home')"><i>🏗️</i><span>TenderBot AI</span></button>
  <div class="hrow"><div class="seg"><button data-lang="mr" onclick="setLang('mr')">मराठी</button><button data-lang="en" onclick="setLang('en')">EN</button></div><button class="avatar" onclick="go('profile')" aria-label="Profile">👤</button></div>
 </div>
 <span class="badge" id="planBadge" style="display:none"></span>
</header>
<main>

<section id="s-welcome" class="screen">
 <div class="hero"><h2 data-i="wTitle"></h2><p data-i="wSub"></p></div>
 <div class="card" id="wStep1">
  <label data-i="chooseLang"></label>
  <div class="langpick"><button data-lang="mr" onclick="setLang('mr')">मराठी</button><button data-lang="en" onclick="setLang('en')">English</button></div>
  <label data-i="yourPhone"></label><input id="w_phone" type="tel" inputmode="tel" autocomplete="tel" placeholder="+919876543210">
  <div class="muted" data-i="phoneHelp" style="margin-top:6px"></div>
  <button class="btn" onclick="sendOtp(this)" data-i="sendOtp"></button>
 </div>
 <div class="card" id="wStep2" style="display:none">
  <p id="otpSentTxt" style="margin-top:0"></p>
  <label data-i="enterCode"></label><input id="w_code" inputmode="numeric" maxlength="8" autocomplete="one-time-code" style="font-size:26px;letter-spacing:8px;text-align:center">
  <button class="btn" onclick="verifyOtp(this)" data-i="verifyLogin"></button>
  <button class="btn sec" onclick="sendOtp(this)" data-i="resend"></button>
  <button class="btn sec" onclick="wStep(1)" data-i="changeNumber"></button>
 </div>
 <div class="card" id="wStep3" style="display:none">
  <h3 style="margin-top:0" data-i="aboutYou"></h3>
  <label data-i="yourName"></label><input id="w_name" autocomplete="name" data-ip="yourNamePh">
  <label data-i="companyName"></label><input id="w_company" autocomplete="organization">
  <label data-i="whichTenders"></label><input id="w_cats" list="cats" data-ip="catsPh">
  <button class="btn" onclick="finishSetup(this)" data-i="continue"></button>
 </div>
 <div id="wRes"></div>
</section>

<section id="s-home" class="screen">
 <div class="hero"><h2 id="hHello"></h2><p data-i="hSub"></p><div class="bar"><i id="hBar"></i></div><p id="hTrial" style="margin-top:8px;font-size:13px"></p></div>
 <div class="stats"><div class="stat"><b id="stPending">–</b><small data-i="stPending"></small></div><div class="stat"><b id="stExpiring">–</b><small data-i="stExpiring"></small></div></div>
 <button class="card" id="hDocs" onclick="go('vault')" style="width:100%;text-align:left;color:inherit">
  <b data-i="hDocsTitle"></b><div class="muted" id="hDocsSub"></div><div class="bar2"><i id="hDocsBar"></i></div></button>
 <div class="tiles">
  <button class="tile" onclick="go('search')"><div class="ic" style="background:#e0f2fe">🔍</div><b data-i="nSearch"></b><small data-i="tSearch"></small></button>
  <button class="tile" onclick="go('predict')"><div class="ic" style="background:#dcfce7">📈</div><b data-i="nBid"></b><small data-i="tBid"></small></button>
  <button class="tile" onclick="go('approval')"><div class="ic" style="background:#fef3c7">✅</div><b data-i="nApprove"></b><small data-i="tApprove"></small></button>
  <button class="tile" onclick="go('vault')"><div class="ic" style="background:#fce7f3">🗂️</div><b data-i="nVault"></b><small data-i="tVault"></small></button>
  <button class="tile" onclick="go('gst')"><div class="ic" style="background:#ede9fe">🧾</div><b data-i="nGst"></b><small data-i="tGst"></small></button>
  <button class="tile" onclick="go('profile')"><div class="ic" style="background:#f1f5f9">👤</div><b data-i="nProfile"></b><small data-i="tProfile"></small></button>
 </div>
</section>

<section id="s-search" class="screen">
 <div class="title"><div class="ic">🔍</div><div><h2 data-i="nSearch"></h2><p data-i="subSearch"></p></div></div>
 <div class="card">
  <div class="sb"><input id="sf_q" data-ip="kwPh" onkeydown="if(event.key==='Enter')doSearch()"><button class="btn" onclick="doSearch(false,this)">🔍</button></div>
  <details style="margin-top:10px"><summary data-i="filters"></summary>
   <div class="grid2"><div><label data-i="category"></label><input id="sf_category" list="cats"></div><div><label data-i="district"></label><input id="sf_district"></div></div>
   <label data-i="department"></label><input id="sf_department" placeholder="PWD, ZP…">
   <div class="grid2"><div><label data-i="minCost"></label><input class="amt" id="sf_min_cost" type="number" inputmode="numeric"></div><div><label data-i="maxCost"></label><input class="amt" id="sf_max_cost" type="number" inputmode="numeric"></div></div>
  </details>
 </div>
 <div id="searchRes"></div>
 <details class="card"><summary>➕ <span data-i="addTender"></span></summary>
  <label data-i="tenderNo"></label><input id="at_id"><label data-i="workName"></label><input id="at_title"><label data-i="department"></label><input id="at_dept">
  <div class="grid2"><div><label data-i="category"></label><input id="at_cat" list="cats"></div><div><label data-i="district"></label><input id="at_dist"></div></div>
  <div class="grid2"><div><label data-i="estCost"></label><input class="amt" id="at_cost" type="number" inputmode="decimal"></div><div><label>EMD (₹)</label><input class="amt" id="at_emd" type="number" inputmode="decimal"></div></div>
  <button class="btn sec" onclick="addTender(this)" data-i="saveTender"></button></details>
 <details class="card"><summary>🌐 <span data-i="importT"></span></summary>
  <p class="muted" data-i="importNote"></p>
  <label data-i="pageLink"></label><input id="im_url" type="url"><div class="grid2"><div><label data-i="category"></label><input id="im_cat" list="cats"></div><div><label data-i="district"></label><input id="im_dist"></div></div>
  <button class="btn sec" onclick="importTenders(this)" data-i="fetchBtn"></button><div id="imRes"></div></details>
</section>

<section id="s-predict" class="screen">
 <div class="title"><div class="ic">📈</div><div><h2 data-i="nBid"></h2><p data-i="subBid"></p></div></div>
 <div class="card">
  <label data-i="category"></label><input id="pr_cat" list="cats" placeholder="civil">
  <label data-i="department"></label><input id="pr_dept" placeholder="PWD">
  <label data-i="workNameOpt"></label><input id="pr_title">
  <div class="grid2"><div><label data-i="estCost"></label><input class="amt" id="pr_est" type="number" inputmode="decimal"></div><div><label data-i="ownCost"></label><input class="amt" id="pr_own" type="number" inputmode="decimal"></div></div>
  <button class="btn" onclick="runPredict(this)" data-i="suggest"></button></div>
 <div id="predRes"></div>
</section>

<section id="s-approval" class="screen">
 <div class="title"><div class="ic">✅</div><div><h2 data-i="nApprove"></h2><p data-i="subApprove"></p></div></div>
 <div class="card">
  <label data-i="tenderNo"></label><input id="ap_id"><label data-i="workName"></label><input id="ap_title">
  <label data-i="bidAmt"></label><input class="amt" id="ap_amt" type="number" inputmode="decimal">
  <div class="row" style="margin-top:14px"><input type="checkbox" id="ap_call" checked><span data-i="alsoCall"></span></div>
  <button class="btn" onclick="reqApproval(this)" data-i="askApproval"></button><div id="apRes"></div></div>
 <h3 data-i="mySubs"></h3><div id="subList"></div>
</section>

<section id="s-vault" class="screen">
 <div class="title"><div class="ic">🗂️</div><div><h2 data-i="nVault"></h2><p data-i="subVault"></p></div></div>
 <div class="card"><b id="vProg"></b><div class="bar2"><i id="vBar"></i></div><div class="muted" data-i="aadhaarNote" style="margin-top:8px"></div></div>
 <div id="vaultList"></div>
 <button class="btn sec" onclick="docDialog(-1)" data-i="addOther"></button>
</section>

<section id="s-gst" class="screen">
 <div class="title"><div class="ic">🧾</div><div><h2 data-i="nGst"></h2><p data-i="subGst"></p></div></div>
 <div class="card">
  <label data-i="taxable"></label><input class="amt" id="g_val" type="number" inputmode="decimal">
  <div class="grid2"><div><label data-i="gstRate"></label><input id="g_rate" type="number" value="18" inputmode="decimal"></div>
  <div><label data-i="supply"></label><select id="g_intra"><option value="1" data-i="intra"></option><option value="0" data-i="inter"></option></select></div></div>
  <div class="row" style="margin-top:14px"><input type="checkbox" id="g_tds"><span data-i="tds"></span></div>
  <h3 data-i="purchases"></h3><div id="g_purch"></div>
  <button class="btn sec" onclick="addPurchase()" data-i="addPurch"></button>
  <button class="btn" onclick="runGst(this)" data-i="calc"></button></div>
 <div id="gstRes"></div>
</section>

<section id="s-profile" class="screen">
 <div class="title"><div class="ic">👤</div><div><h2 data-i="nProfile"></h2><p data-i="tProfile"></p></div></div>
 <div class="card">
  <label data-i="yourPhone"></label><input id="pf_phone" readonly>
  <label data-i="yourName"></label><input id="pf_name">
  <label data-i="companyName"></label><input id="pf_company">
  <div class="grid2"><div><label data-i="cls"></label><input id="pf_class" placeholder="Class 1"></div><div><label data-i="turnover"></label><input class="amt" id="pf_turn" type="number" inputmode="decimal"></div></div>
  <label data-i="cats"></label><input id="pf_cats" placeholder="civil, road"><label data-i="dists"></label><input id="pf_dists" data-ip="distsPh">
  <button class="btn" onclick="saveProfile(this)" data-i="save"></button>
  <button class="btn sec" onclick="go('vault')" data-i="myDocsBtn"></button>
  <button class="btn sec" id="installBtn" style="display:none" onclick="installApp()" data-i="install"></button>
  <button class="btn sec" onclick="logout()" data-i="logout"></button>
  <div id="pfRes"></div></div>
</section>
</main>

<nav>
 <button data-s="home" onclick="go('home')"><span>🏠</span><em style="font-style:normal" data-i="nHome"></em></button>
 <button data-s="search" onclick="go('search')"><span>🔍</span><em style="font-style:normal" data-i="nSearchS"></em></button>
 <button data-s="predict" onclick="go('predict')"><span>📈</span><em style="font-style:normal" data-i="nBidS"></em></button>
 <button data-s="approval" onclick="go('approval')"><span>✅</span><em style="font-style:normal" data-i="nApproveS"></em></button>
 <button data-s="vault" onclick="go('vault')"><span>🗂️</span><em style="font-style:normal" data-i="nVaultS"></em></button>
 <button data-s="gst" onclick="go('gst')"><span>🧾</span><em style="font-style:normal">GST</em></button>
</nav>
<datalist id="cats"><option>civil</option><option>road</option><option>building</option><option>water supply</option><option>electrical</option><option>sand</option><option>material supply</option><option>labour</option></datalist>
<button id="chatFab" onclick="openChat()" aria-label="AI">💬</button>
<dialog id="chatDlg" class="chat">
 <div class="ch"><span data-i="chatTitle"></span><button onclick="$('#chatDlg').close()" aria-label="close">✕</button></div>
 <div id="chatLog"></div><div class="chips" id="chatChips"></div>
 <div class="cin"><input id="chatIn" data-ip="chatPh" onkeydown="if(event.key==='Enter')sendChat()"><button onclick="sendChat()">➤</button></div>
</dialog>
<div id="toast"></div><dialog id="dlg"></dialog>

<script>
/* ================= i18n ================= */
const I={
mr:{
sendOtp:'OTP पाठवा',otpSent:'{p} वर SMS ने OTP पाठवला आहे',enterCode:'OTP टाका',verifyLogin:'तपासा आणि लॉगिन करा',resend:'OTP पुन्हा पाठवा',changeNumber:'नंबर बदला',aboutYou:'तुमची माहिती',companyName:'कंपनी / फर्मचे नाव',whichTenders:'कोणत्या प्रकारचे टेंडर हवेत?',catsPh:'उदा. civil, road, building',continue:'पुढे चला',logout:'लॉगआउट',sessionExpired:'सेशन संपले. कृपया पुन्हा लॉगिन करा.',
chatTitle:'🤖 AI सहाय्यक',chatPh:'तुमचा प्रश्न लिहा…',chatHello:'नमस्कार भाऊ! मी टेंडर, कागदपत्रे आणि GST बद्दल मदत करू शकतो. काय विचारायचे आहे?',chip1:'टेंडरसाठी कोणती कागदपत्रे लागतात?',chip2:'माझे कोणते कागदपत्र संपत आहे?',chip3:'EMD म्हणजे काय?',
vProg:'कागदपत्रे पूर्ण: {n}/{m}',missingDoc:'जोडलेले नाही',noFile:'फाइल नाही',add:'जोडा',addOther:'➕ दुसरे कागदपत्र जोडा',viewTitle:'कागदपत्र',download:'डाउनलोड',fileLabel:'फाइल (फोटो/PDF, कमाल 5 MB)',needType:'कागदपत्राचा प्रकार लिहा.',aadhaarNote:'🔒 कागदपत्रे एन्क्रिप्ट करून ठेवली जातात. आधार नंबर सेव्ह केला जात नाही, फक्त फाइल.',dt_aadhaar:'आधार कार्ड',e413:'फाइल खूप मोठी आहे (कमाल 5 MB)',e415:'फक्त PDF, JPG, PNG किंवा WEBP चालते',e429:'खूप प्रयत्न झाले. थोड्या वेळाने पुन्हा करा',e400:'चुकीची माहिती / OTP',delConfirm:'हे कागदपत्र काढायचे?',hDocsTitle:'🗂️ माझी कागदपत्रे',hDocsSub:'{n}/{m} पूर्ण — बाकी जोडा',myDocsBtn:'🗂️ कागदपत्रे अपलोड करा',
wTitle:'नमस्कार! TenderBot मध्ये स्वागत',wSub:'कंत्राटदाराचा हक्काचा आणि विश्वासू डिजिटल मॅनेजर',chooseLang:'भाषा निवडा',yourName:'तुमचे / फर्मचे नाव',yourNamePh:'उदा. श्री साई कन्स्ट्रक्शन',yourPhone:'WhatsApp नंबर',phoneHelp:'अलर्ट आणि मंजुरीचे संदेश याच नंबरवर येतील. १५ दिवस मोफत ट्रायल.',start:'सुरू करा',
hHello:'नमस्कार, {n}!',hHelloAnon:'नमस्कार!',hSub:'आज काय करायचे आहे?',stPending:'मंजुरीसाठी प्रलंबित',stExpiring:'लवकरच संपणारी कागदपत्रे',
nHome:'होम',nSearch:'टेंडर शोध',nSearchS:'शोध',nBid:'बिड रेट',nBidS:'बिड रेट',nApprove:'सबमिशन मंजुरी',nApproveS:'मंजुरी',nVault:'कागदपत्र व्हॉल्ट',nVaultS:'व्हॉल्ट',nGst:'GST सल्ला',nProfile:'माझे प्रोफाइल',
tSearch:'नवीन टेंडर शोधा',tBid:'AI कडून योग्य रेट',tApprove:'भरण्यापूर्वी अंतिम OK',tVault:'परवाने सुरक्षित ठेवा',tGst:'बिल आणि टॅक्स हिशोब',tProfile:'नंबर, वर्ग, उलाढाल',
subSearch:'कीवर्ड आणि फिल्टरने टेंडर शोधा',subBid:'जुन्या अवार्ड डेटावरून अंदाजे L1 रेट',subApprove:'तुमच्या OK शिवाय काहीही सबमिट होत नाही',subVault:'मुदत संपण्याच्या ३० दिवस आधी अलर्ट',subGst:'GST देय, ITC आणि सीए-रेडी तपशील',
trialDay:'ट्रायल: दिवस {d}/{n}',trialLeft:'मोफत ट्रायल — दिवस {d}/{n}',planVip:'VIP',planBasic:'Basic',trialEnded:'ट्रायल संपली',
kwPh:'कीवर्ड: रस्ता, पूल, पाणीपुरवठा…',filters:'फिल्टर',category:'श्रेणी',district:'जिल्हा',department:'विभाग',minCost:'किमान किंमत (₹)',maxCost:'कमाल किंमत (₹)',
found:'{n} टेंडर सापडले',emptyTenders:'या शोधाला कोणतेही टेंडर नाही',emptySub:'खाली "नवीन टेंडर जोडा" किंवा पोर्टल लिंक वापरा.',addTender:'नवीन टेंडर जोडा',tenderNo:'टेंडर क्रमांक',workName:'कामाचे नाव',estCost:'अंदाजित किंमत (₹)',saveTender:'टेंडर सेव्ह करा',tenderSaved:'टेंडर सेव्ह झाले',
importT:'पोर्टल लिंकवरून आणा',importNote:'फक्त mahatenders.gov.in / eprocure.gov.in चे सार्वजनिक यादी-पेज चालते.',pageLink:'पेज लिंक',fetchBtn:'आणा',imported:'{c} ओळी सापडल्या, {s} नवीन सेव्ह झाल्या.',
aBid:'📈 बिड रेट',aElig:'📋 पात्रता',aApprove:'✅ मंजुरी',
eligTitle:'📋 पात्रता तपासणी',reqDocs:'निविदेत मागितलेली कागदपत्रे (प्रत्येक वेगळ्या ओळीत)',reqDocsPh:'GST Registration\nPAN Card\nEPF Certificate',minClass:'किमान वर्ग',minTurn:'किमान उलाढाल (₹)',heldNote:'व्हॉल्टमधील कागदपत्रे: {n}',check:'तपासा',close:'बंद करा',needDoc:'किमान एक कागदपत्र लिहा.',eligible:'पात्र',notEligible:'अपात्र / त्रुटी',incomplete:'तपासणी अपूर्ण',missing:'❌ कमी कागदपत्रे',have:'✅ उपलब्ध',
workNameOpt:'कामाचे नाव (ऐच्छिक)',ownCost:'माझा खर्च अंदाज (₹)',suggest:'रेट सुचवा',needCatEst:'श्रेणी आणि अंदाजित किंमत आवश्यक आहे.',noData:'जुना डेटा उपलब्ध नाही',noDataSub:'सापडलेले नमुने: {n} (किमान {m} हवेत). अवार्ड डेटा भरल्यावर अंदाज दिसेल.',
sAgg:'आक्रमक (जिंकण्याची शक्यता जास्त)',sRec:'सुचवलेला (अंदाजे L1)',sCon:'सावध (नफा जास्त)',rate:'रेट',bidAmt:'बिड रक्कम (₹)',profit:'नफा',margin:'मार्जिन',basis:'आधार: {n} अवार्ड्स · {s}',winners:'वारंवार जिंकणारे',
alsoCall:'मराठी व्हॉइस कॉलही करा',askApproval:'मंजुरी मागवा',mySubs:'माझी सबमिशन्स',noSubs:'अजून कोणतेही सबमिशन नाही.',yes:'होय, सबमिट करा',no:'नाही, रद्द करा',confirmYes:'खात्री आहे? बिड मंजूर होईल.',confirmNo:'हे सबमिशन रद्द करायचे?',
asked:'भाऊ, {a} चे टेंडर सबमिट करू का?',dry:'⚠️ Twilio जोडलेले नाही — WhatsApp/कॉल पाठवला गेला नाही. खाली ॲपमध्येच मंजुरी द्या.',
st_PENDING:'मंजुरी प्रलंबित',st_CANCELLED:'रद्द',st_APPROVED_AWAITING_PORTAL_SUBMISSION:'मंजूर — पोर्टल सबमिशन बाकी',st_SUBMITTED:'सबमिट झाले',st_APPROVED_SUBMISSION_FAILED:'सबमिशन अयशस्वी',
vaultEmpty:'व्हॉल्ट रिकामा आहे',vaultEmptySub:'खाली कागदपत्र जोडा. मुदत संपण्याच्या ३० दिवस आधी WhatsApp अलर्ट येतो.',addDocT:'कागदपत्र जोडा',docType:'प्रकार',docOther:'किंवा दुसरा प्रकार लिहा',docNo:'क्रमांक',docExp:'मुदत संपण्याची तारीख',docLink:'फाइल/ड्राइव्ह लिंक (ऐच्छिक)',addBtn:'जोडा',docAdded:'कागदपत्र जोडले',
vs_valid:'वैध',vs_expiring_soon:'लवकरच संपणार',vs_expired:'संपले',vs_no_expiry:'मुदत नाही',daysLeft:'{n} दिवस',expOn:'मुदत: {d}',noLabel:'क्र. {n}',openFile:'फाइल उघडा',
dt_gst:'GST नोंदणी',dt_pan:'PAN कार्ड',dt_pwd:'PWD नोंदणी',dt_c1:'Class-1 प्रमाणपत्र',dt_epf:'EPF',dt_esic:'ESIC',dt_lab:'कामगार परवाना',dt_sol:'सॉल्व्हन्सी प्रमाणपत्र',dt_turn:'उलाढाल प्रमाणपत्र',dt_itr:'आयकर रिटर्न (ITR)',dt_udyam:'उद्योग / Udyam',dt_dsc:'डिजिटल सही (DSC)',
taxable:'करपात्र मूल्य (₹)',gstRate:'GST दर (%)',supply:'पुरवठा',intra:'राज्यांतर्गत (CGST+SGST)',inter:'आंतरराज्य (IGST)',tds:'सरकारी विभाग GST TDS कापतो',purchases:'खरेदी (ITC साठी)',purchName:'खरेदीचे नाव (उदा. सिमेंट)',value:'मूल्य (₹)',itcOk:'ITC पात्र',remove:'काढा',addPurch:'+ खरेदी जोडा',calc:'हिशोब करा',
result:'निकाल',outGst:'आउटपुट GST',eligItc:'पात्र ITC',netPay:'निव्वळ GST देय',receipt:'मिळणारी रक्कम',caDetails:'सीए-रेडी तपशील',shareCA:'📤 सीए ला शेअर करा',planning:'टॅक्स नियोजन सूचना',copied:'कॉपी केले',draftOnly:'फक्त ड्राफ्ट उपलब्ध',purchDefault:'खरेदी',
cls:'वर्ग',turnover:'वार्षिक उलाढाल (₹)',cats:'श्रेणी (स्वल्पविरामाने)',dists:'जिल्हे (स्वल्पविरामाने)',distsPh:'पुणे, सातारा',save:'सेव्ह करा',saved:'सेव्ह झाले ✔',install:'📲 ॲप इन्स्टॉल करा',
needPhone:'आधी तुमचा WhatsApp नंबर टाका',loading:'लोड होत आहे…',lakh:'लाख',crore:'कोटी',
paywall:'भाऊ, तुमची १५ दिवसांची मोफत ट्रायल संपली आहे. पुढे टेंडर सबमिशन, व्हॉट्सॲप/कॉल अलर्ट आणि सीए-रेडी जीएसटी बिलिंग चालू ठेवण्यासाठी तुमचा ₹९९९ किंवा ₹५,००० चा प्लॅन सुरू करा.',upgradeVip:'भाऊ, हे फीचर VIP Premium (₹५,०००/महिना) प्लॅनमध्ये मिळते. VIP प्लॅनवर अपग्रेड करा.',
netErr:'सर्व्हरशी संपर्क होत नाही. इंटरनेट तपासा; सर्व्हर झोपला असल्यास १ मिनिट थांबून पुन्हा करा.',checkInputs:'कृपया माहिती तपासा',e404:'सापडले नाही',e502:'पेज वाचता आले नाही',e503:'ही सेवा सध्या उपलब्ध नाही',e401:'परवानगी नाही',e500:'काहीतरी चुकले ({s})',
desc_below:'SSR/अंदाजित दरापेक्षा {p}% कमी',desc_above:'SSR/अंदाजित दरापेक्षा {p}% जास्त',desc_eq:'SSR/अंदाजित दराइतका',
},
en:{
sendOtp:'Send OTP',otpSent:'OTP sent by SMS to {p}',enterCode:'Enter OTP',verifyLogin:'Verify & log in',resend:'Resend OTP',changeNumber:'Change number',aboutYou:'About you',companyName:'Company / firm name',whichTenders:'Which kind of tenders do you want?',catsPh:'e.g. civil, road, building',continue:'Continue',logout:'Log out',sessionExpired:'Session expired. Please log in again.',
chatTitle:'🤖 AI assistant',chatPh:'Type your question…',chatHello:'Hello! I can help with tenders, documents and GST. What would you like to ask?',chip1:'Which documents does a tender need?',chip2:'Which of my documents is expiring?',chip3:'What is EMD?',
vProg:'Documents complete: {n}/{m}',missingDoc:'Not added',noFile:'No file',add:'Add',addOther:'➕ Add another document',viewTitle:'Document',download:'Download',fileLabel:'File (photo/PDF, max 5 MB)',needType:'Enter the document type.',aadhaarNote:'🔒 Documents are stored encrypted. Your Aadhaar number is not saved, only the file.',dt_aadhaar:'Aadhaar card',e413:'File too large (max 5 MB)',e415:'Only PDF, JPG, PNG or WEBP allowed',e429:'Too many attempts. Please try again later',e400:'Wrong details / OTP',delConfirm:'Remove this document?',hDocsTitle:'🗂️ My documents',hDocsSub:'{n}/{m} done — add the rest',myDocsBtn:'🗂️ Upload my documents',
wTitle:'Welcome to TenderBot!',wSub:'Your trusted digital manager for contractors',chooseLang:'Choose language',yourName:'Your / firm name',yourNamePh:'e.g. Shri Sai Construction',yourPhone:'WhatsApp number',phoneHelp:'Alerts and approval messages will come to this number. 15-day free trial.',start:'Get started',
hHello:'Hello, {n}!',hHelloAnon:'Hello!',hSub:'What would you like to do today?',stPending:'Pending approvals',stExpiring:'Documents expiring soon',
nHome:'Home',nSearch:'Tender Search',nSearchS:'Search',nBid:'Bid Rate',nBidS:'Bid Rate',nApprove:'Submission Approval',nApproveS:'Approve',nVault:'Document Vault',nVaultS:'Vault',nGst:'GST Advice',nProfile:'My Profile',
tSearch:'Find new tenders',tBid:'Right rate from AI',tApprove:'Final OK before filing',tVault:'Keep licences safe',tGst:'Billing & tax workings',tProfile:'Number, class, turnover',
subSearch:'Search tenders by keyword and filters',subBid:'Predicted L1 rate from past awards',subApprove:'Nothing is submitted without your OK',subVault:'Alerts 30 days before expiry',subGst:'GST payable, ITC and CA-ready details',
trialDay:'Trial: day {d}/{n}',trialLeft:'Free trial — day {d}/{n}',planVip:'VIP',planBasic:'Basic',trialEnded:'Trial ended',
kwPh:'Keyword: road, bridge, water supply…',filters:'Filters',category:'Category',district:'District',department:'Department',minCost:'Min cost (₹)',maxCost:'Max cost (₹)',
found:'{n} tenders found',emptyTenders:'No tenders match this search',emptySub:'Use "Add new tender" or a portal link below.',addTender:'Add new tender',tenderNo:'Tender number',workName:'Name of work',estCost:'Estimated cost (₹)',saveTender:'Save tender',tenderSaved:'Tender saved',
importT:'Import from portal link',importNote:'Only public list pages of mahatenders.gov.in / eprocure.gov.in work.',pageLink:'Page link',fetchBtn:'Import',imported:'{c} rows found, {s} new saved.',
aBid:'📈 Bid rate',aElig:'📋 Eligibility',aApprove:'✅ Approve',
eligTitle:'📋 Eligibility check',reqDocs:'Documents required by the tender (one per line)',reqDocsPh:'GST Registration\nPAN Card\nEPF Certificate',minClass:'Minimum class',minTurn:'Minimum turnover (₹)',heldNote:'Documents in your vault: {n}',check:'Check',close:'Close',needDoc:'Enter at least one document.',eligible:'Eligible',notEligible:'Not eligible / gaps',incomplete:'Check incomplete',missing:'❌ Missing documents',have:'✅ Available',
workNameOpt:'Name of work (optional)',ownCost:'My cost estimate (₹)',suggest:'Suggest rate',needCatEst:'Category and estimated cost are required.',noData:'No past data available',noDataSub:'Samples found: {n} (at least {m} needed). The estimate appears once award data is loaded.',
sAgg:'Aggressive (higher chance to win)',sRec:'Recommended (predicted L1)',sCon:'Conservative (more profit)',rate:'Rate',bidAmt:'Bid amount (₹)',profit:'Profit',margin:'Margin',basis:'Basis: {n} awards · {s}',winners:'Frequent winners',
alsoCall:'Also place a Marathi voice call',askApproval:'Ask for approval',mySubs:'My submissions',noSubs:'No submissions yet.',yes:'Yes, submit',no:'No, cancel',confirmYes:'Are you sure? The bid will be approved.',confirmNo:'Cancel this submission?',
asked:'Shall I submit the {a} tender?',dry:'⚠️ Twilio is not connected — no WhatsApp/call was sent. Approve inside the app below.',
st_PENDING:'Awaiting approval',st_CANCELLED:'Cancelled',st_APPROVED_AWAITING_PORTAL_SUBMISSION:'Approved — portal submission pending',st_SUBMITTED:'Submitted',st_APPROVED_SUBMISSION_FAILED:'Submission failed',
vaultEmpty:'Your vault is empty',vaultEmptySub:'Add a document below. You get a WhatsApp alert 30 days before expiry.',addDocT:'Add a document',docType:'Type',docOther:'Or type another kind',docNo:'Number',docExp:'Expiry date',docLink:'File / drive link (optional)',addBtn:'Add',docAdded:'Document added',
vs_valid:'Valid',vs_expiring_soon:'Expiring soon',vs_expired:'Expired',vs_no_expiry:'No expiry',daysLeft:'{n} days',expOn:'Expires: {d}',noLabel:'No. {n}',openFile:'Open file',
dt_gst:'GST registration',dt_pan:'PAN card',dt_pwd:'PWD registration',dt_c1:'Class-1 certificate',dt_epf:'EPF',dt_esic:'ESIC',dt_lab:'Labour licence',dt_sol:'Solvency certificate',dt_turn:'Turnover certificate',dt_itr:'Income tax return (ITR)',dt_udyam:'Udyam registration',dt_dsc:'Digital signature (DSC)',
taxable:'Taxable value (₹)',gstRate:'GST rate (%)',supply:'Supply',intra:'Within state (CGST+SGST)',inter:'Inter-state (IGST)',tds:'Government department deducts GST TDS',purchases:'Purchases (for ITC)',purchName:'Purchase name (e.g. cement)',value:'Value (₹)',itcOk:'ITC eligible',remove:'Remove',addPurch:'+ Add purchase',calc:'Calculate',
result:'Result',outGst:'Output GST',eligItc:'Eligible ITC',netPay:'Net GST payable',receipt:'Amount received',caDetails:'CA-ready breakdown',shareCA:'📤 Share with CA',planning:'Tax planning tips',copied:'Copied',draftOnly:'Draft only',purchDefault:'Purchase',
cls:'Class',turnover:'Annual turnover (₹)',cats:'Categories (comma separated)',dists:'Districts (comma separated)',distsPh:'Pune, Satara',save:'Save',saved:'Saved ✔',install:'📲 Install app',
needPhone:'Please enter your WhatsApp number first',loading:'Loading…',lakh:'lakh',crore:'crore',
paywall:'Your 15-day free trial has ended. Start the ₹999 or ₹5,000 plan to continue tender submission, WhatsApp/call alerts and CA-ready GST billing.',upgradeVip:'This feature is part of the VIP Premium plan (₹5,000/month). Please upgrade.',
netErr:'Cannot reach the server. Check your internet; if the server was asleep, wait a minute and retry.',checkInputs:'Please check the details',e404:'Not found',e502:'Could not read the page',e503:'This service is not available right now',e401:'Not allowed',e500:'Something went wrong ({s})',
desc_below:'{p}% below the estimate (SSR)',desc_above:'{p}% above the estimate (SSR)',desc_eq:'equal to the estimate (SSR)',
}};
let lang=localStorage.getItem('tb_lang')||'mr';
const t=(k,v)=>{let s=(I[lang][k]??I.mr[k]??k);if(v)for(const x in v)s=s.split('{'+x+'}').join(v[x]);return s};

/* ================= helpers ================= */
const $=s=>document.querySelector(s);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const inr=n=>n==null?'—':'₹'+Number(n).toLocaleString('en-IN',{maximumFractionDigits:2});
const num=id=>{const v=$('#'+id).value.trim();return v===''?null:Number(v)};
const val=id=>$('#'+id).value.trim();
const L=(mr,en)=>lang==='mr'?mr:en;
let phone=localStorage.getItem('tb_phone')||'';
let profile=JSON.parse(localStorage.getItem('tb_profile')||'{}');
let planInfo=null, vaultDocs=[], lastTenders=[], deferredInstall=null, cur='home';

function toast(m){const x=$('#toast');x.textContent=m;x.style.display='block';clearTimeout(toast.h);toast.h=setTimeout(()=>x.style.display='none',3800)}
function setPlan(d){planInfo=d;const b=$('#planBadge'),s=d.plan_status;
  b.style.display='inline-block';b.textContent=s==='trial'?t('trialDay',{d:d.trial_day,n:d.trial_days_total||15}):s==='expired'?t('trialEnded'):s==='vip'?t('planVip'):t('planBasic');
  drawTrial()}
function drawTrial(){if(!planInfo)return;const n=planInfo.trial_days_total||15,d=Math.min(planInfo.trial_day,n);
  $('#hBar').style.width=(planInfo.plan_status==='trial'?d/n*100:100)+'%';
  $('#hTrial').textContent=planInfo.plan_status==='trial'?t('trialLeft',{d,n}):planInfo.plan_status==='expired'?t('trialEnded'):(planInfo.plan_status==='vip'?t('planVip'):t('planBasic'))}
function statusMsg(s){return s===400?t('e400'):s===401||s===403?t('e401'):s===404?t('e404'):s===413?t('e413'):s===415?t('e415'):s===429?t('e429'):s===502?t('e502'):s===503?t('e503'):t('e500',{s})}
const tok=()=>localStorage.getItem('tb_token')||'';
function authH(json){const h={};if(tok())h['Authorization']='Bearer '+tok();if(json)h['Content-Type']='application/json';return h}
async function api(path,method='GET',body,form){
  let r;try{r=await fetch(path,{method,headers:authH(!form),body:form?form:(body?JSON.stringify(body):undefined)})}catch(e){throw new Error(t('netErr'))}
  let d=null;try{d=await r.json()}catch(e){}
  if(!r.ok){const det=d&&d.detail;
    if(r.status===401&&!path.startsWith('/auth/')){forceLogin();throw new Error(t('sessionExpired'))}
    if(r.status===402&&det&&det.message_mr){if(det.plan_status)setPlan(det);const e=new Error(det.plan_status==='basic'?t('upgradeVip'):t('paywall'));e.paywall=true;throw e}
    if(r.status===422&&Array.isArray(det))throw new Error(t('checkInputs')+': '+det.map(x=>((x.loc||[]).slice(-1)[0]||'')).filter(Boolean).join(', '));
    if(r.status===422)throw new Error(typeof det==='string'&&lang==='mr'?det:t('checkInputs'));
    throw new Error(typeof det==='string'&&lang==='mr'?det:statusMsg(r.status))}
  if(d&&d.plan_status)setPlan(d);return d}
function fail(id,e){$('#'+id).innerHTML=`<div class="${e.paywall?'pay':'err'}">${esc(e.message)}</div>`}
async function busy(btn,fn){if(btn)btn.classList.add('loading');try{await fn()}finally{if(btn)btn.classList.remove('loading')}}
function needPhone(){if(phone)return true;toast(t('needPhone'));go('welcome');return false}
function hint(v){const n=Number(v);if(!v||isNaN(n)||n<=0)return'';
  let extra='';if(n>=1e7)extra=' ('+(n/1e7).toLocaleString('en-IN',{maximumFractionDigits:2})+' '+t('crore')+')';else if(n>=1e5)extra=' ('+(n/1e5).toLocaleString('en-IN',{maximumFractionDigits:2})+' '+t('lakh')+')';
  return inr(n)+extra}
function wireAmounts(root){(root||document).querySelectorAll('input.amt').forEach(i=>{if(i.dataset.w)return;i.dataset.w=1;const h=document.createElement('div');h.className='hint';i.after(h);i.addEventListener('input',()=>h.textContent=hint(i.value))})}
const descPct=p=>p<0?t('desc_below',{p:Math.abs(p).toFixed(1)}):p>0?t('desc_above',{p:p.toFixed(1)}):t('desc_eq');

/* ================= navigation / language ================= */
const list=s=>s.split(',').map(x=>x.trim()).filter(Boolean);
const profFrom=d=>({name:d.name,company_name:d.company_name,contractor_class:d.contractor_class,annual_turnover:d.annual_turnover,categories:d.categories||[],districts:d.districts||[]});
const saveLocal=()=>localStorage.setItem('tb_profile',JSON.stringify(profile));
const loggedIn=()=>!!(phone&&tok());
function applyLang(){
  document.documentElement.lang=lang;
  document.querySelectorAll('[data-i]').forEach(e=>e.textContent=t(e.dataset.i));
  document.querySelectorAll('[data-ip]').forEach(e=>e.placeholder=t(e.dataset.ip));
  document.querySelectorAll('[data-lang]').forEach(b=>b.classList.toggle('on',b.dataset.lang===lang));
  const ta=$('#an_docs');if(ta)ta.placeholder=t('reqDocsPh');
  $('#hHello').textContent=profile.name?t('hHello',{n:profile.name}):t('hHelloAnon');
  if(planInfo)setPlan(planInfo);
}
function setLang(l){lang=l;localStorage.setItem('tb_lang',l);applyLang();['predRes','gstRes','apRes','anRes','imRes'].forEach(i=>{const e=$('#'+i);if(e)e.innerHTML=''});if(loggedIn()){renderChips();go(cur,true)}}
function go(id,keep){
  if(!loggedIn()&&id!=='welcome')id='welcome';
  cur=id;
  document.body.classList.toggle('anon',!loggedIn());
  document.querySelectorAll('.screen').forEach(s=>s.classList.toggle('on',s.id==='s-'+id));
  document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('on',b.dataset.s===id));
  if(!keep)window.scrollTo(0,0);
  if(id==='home')loadHome();
  if(id==='approval')loadSubs();
  if(id==='vault')loadVault();
  if(id==='search'&&(!lastTenders.length||keep))doSearch(true);
  if(id==='profile')fillProfile();
}

/* ================= login (SMS OTP) / onboarding ================= */
let otpPhone='';
function wStep(n){[1,2,3].forEach(i=>$('#wStep'+i).style.display=i===n?'block':'none');$('#wRes').innerHTML=''}
async function sendOtp(btn){
  const p=($('#wStep1').style.display!=='none'?val('w_phone'):otpPhone)||val('w_phone');
  if(!p){$('#wRes').innerHTML=`<div class="err">${esc(t('needPhone'))}</div>`;return}
  await busy(btn,async()=>{try{const d=await api('/auth/send-otp','POST',{phone:p});otpPhone=d.phone;$('#otpSentTxt').textContent=t('otpSent',{p:d.phone});wStep(2);$('#w_code').value='';$('#w_code').focus()}catch(e){fail('wRes',e)}})}
async function verifyOtp(btn){
  const code=val('w_code');if(code.length<4)return;
  await busy(btn,async()=>{try{const d=await api('/auth/verify-otp','POST',{phone:otpPhone,code});
    localStorage.setItem('tb_token',d.token);phone=d.phone;localStorage.setItem('tb_phone',phone);
    profile=profFrom(d.profile);saveLocal();setPlan(d.profile);applyLang();
    if(!d.profile.name)wStep(3);else go('home')}catch(e){fail('wRes',e)}})}
async function finishSetup(btn){
  await busy(btn,async()=>{try{const d=await api('/me','POST',{name:val('w_name')||null,company_name:val('w_company')||null,categories:list(val('w_cats')),language:lang});
    profile=profFrom(d);saveLocal();applyLang();go('home')}catch(e){fail('wRes',e)}})}
function forceLogin(){['tb_token','tb_phone','tb_profile'].forEach(k=>localStorage.removeItem(k));phone='';profile={};planInfo=null;lastTenders=[];vaultDocs=[];chatHist=[];
  $('#planBadge').style.display='none';wStep(1);go('welcome')}
async function logout(){try{await api('/auth/logout','POST')}catch(e){}forceLogin()}

/* ================= home / profile ================= */
async function loadHome(){
  $('#hHello').textContent=profile.name?t('hHello',{n:profile.name}):t('hHelloAnon');
  try{const d=await api('/submissions');$('#stPending').textContent=d.submissions.filter(s=>s.status==='PENDING').length}catch(e){$('#stPending').textContent='–'}
  try{const v=await api('/vault/documents');vaultDocs=v.documents;$('#stExpiring').textContent=v.expiring_within_alert_window.length;
    const done=STD.filter(x=>v.documents.some(d=>d.doc_type===x[0]&&d.has_file)).length;
    $('#hDocsSub').textContent=t('hDocsSub',{n:done,m:STD.length});$('#hDocsBar').style.width=(done/STD.length*100)+'%'}catch(e){$('#stExpiring').textContent='–'}}
function fillProfile(){$('#pf_phone').value=phone;$('#pf_name').value=profile.name||'';$('#pf_company').value=profile.company_name||'';$('#pf_class').value=profile.contractor_class||'';$('#pf_turn').value=profile.annual_turnover??'';$('#pf_cats').value=(profile.categories||[]).join(', ');$('#pf_dists').value=(profile.districts||[]).join(', ');$('#pf_turn').dispatchEvent(new Event('input'))}
async function saveProfile(btn){
  await busy(btn,async()=>{try{const d=await api('/me','POST',{name:val('pf_name')||null,company_name:val('pf_company')||null,contractor_class:val('pf_class')||null,annual_turnover:num('pf_turn'),categories:list(val('pf_cats')),districts:list(val('pf_dists')),language:lang});
    profile=profFrom(d);saveLocal();applyLang();$('#pfRes').innerHTML=`<div class="info">${esc(t('saved'))}</div>`;toast(t('saved'))}catch(e){fail('pfRes',e)}})}
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();deferredInstall=e;$('#installBtn').style.display='block'});
function installApp(){if(deferredInstall){deferredInstall.prompt();deferredInstall=null}}

/* ================= 1. Tender search ================= */
async function doSearch(silent,btn){
  const p=new URLSearchParams();
  [['q','sf_q'],['category','sf_category'],['district','sf_district'],['department','sf_department'],['min_cost','sf_min_cost'],['max_cost','sf_max_cost']].forEach(([k,i])=>{const v=val(i);if(v)p.set(k,v)});
  await busy(btn,async()=>{try{const d=await api('/tenders/search?'+p);lastTenders=d.tenders;
    $('#searchRes').innerHTML=d.tenders.length?`<p class="muted" style="margin:0 4px 8px">${esc(t('found',{n:d.count}))}</p>`+d.tenders.map((x,i)=>`<div class="card"><b>${esc(x.title)}</b>
      <div class="muted">${esc(x.tender_id)} · ${esc(x.department)}</div>
      <div class="kpi"><div><small>${esc(t('estCost'))}</small><b>${inr(x.estimated_cost)}</b></div><div><small>EMD</small><b>${inr(x.emd_amount)}</b></div></div>
      <span class="chip">${esc(x.category)}</span>${x.district?`<span class="chip">${esc(x.district)}</span>`:''}
      <div><button class="btn sm sec" onclick="toPredict(${i})">${t('aBid')}</button><button class="btn sm sec" onclick="openAnalyze(${i})">${t('aElig')}</button><button class="btn sm" onclick="toApproval(${i})">${t('aApprove')}</button></div></div>`).join('')
      :`<div class="card empty"><span class="big">🗒️</span><b>${esc(t('emptyTenders'))}</b><div>${esc(t('emptySub'))}</div></div>`}
  catch(e){if(!silent)fail('searchRes',e)}})}
async function addTender(btn){if(!needPhone())return;
  await busy(btn,async()=>{try{await api('/tenders','POST',{phone,tender_id:val('at_id'),title:val('at_title'),department:val('at_dept'),category:val('at_cat')||'general',district:val('at_dist')||null,estimated_cost:num('at_cost'),emd_amount:num('at_emd')});
    toast(t('tenderSaved'));['at_id','at_title','at_dept','at_cat','at_dist','at_cost','at_emd'].forEach(i=>{$('#'+i).value='';$('#'+i).dispatchEvent(new Event('input'))});doSearch(true)}catch(e){toast(e.message)}})}
async function importTenders(btn){await busy(btn,async()=>{
  try{const d=await api('/discover-tenders','POST',{url:val('im_url'),category:val('im_cat')||null,district:val('im_dist')||null,save:true});
    $('#imRes').innerHTML=`<div class="info">${esc(t('imported',{c:d.count,s:d.saved}))}</div>`;doSearch(true)}catch(e){fail('imRes',e)}})}
function toPredict(i){const x=lastTenders[i];$('#pr_cat').value=x.category;$('#pr_dept').value=x.department;$('#pr_title').value=x.title;$('#pr_est').value=x.estimated_cost;$('#pr_est').dispatchEvent(new Event('input'));go('predict')}
function toApproval(i){const x=lastTenders[i];$('#ap_id').value=x.tender_id;$('#ap_title').value=x.title;$('#ap_amt').value='';go('approval')}
async function openAnalyze(i){
  if(!needPhone())return;const x=lastTenders[i];await loadVault(true);
  const d=$('#dlg');d.innerHTML=`<h2 style="margin-top:0">${t('eligTitle')}</h2><p class="muted">${esc(x.title)}</p>
   <label>${t('reqDocs')}</label><textarea id="an_docs" rows="5" placeholder="${esc(t('reqDocsPh'))}"></textarea>
   <div class="grid2"><div><label>${t('minClass')}</label><input id="an_class" placeholder="Class 1"></div><div><label>${t('minTurn')}</label><input id="an_turn" type="number"></div></div>
   <p class="muted">${esc(t('heldNote',{n:vaultDocs.length}))}</p>
   <button class="btn" id="an_go">${t('check')}</button><button class="btn sec" onclick="$('#dlg').close()">${t('close')}</button><div id="anRes"></div>`;
  d.showModal();
  $('#an_go').onclick=()=>busy($('#an_go'),async()=>{
    const docs=val('an_docs').split('\n').map(s=>s.trim()).filter(Boolean);
    if(!docs.length){$('#anRes').innerHTML=`<div class="err">${esc(t('needDoc'))}</div>`;return}
    try{const r=await api('/analyze-tender','POST',{vendor:{phone,name:profile.name||'Contractor',contractor_class:profile.contractor_class||null,categories:profile.categories||[],districts:profile.districts||[],annual_turnover:profile.annual_turnover??null,documents_held:vaultDocs.map(v=>v.doc_type)},
      tender:{tender_id:x.tender_id,title:x.title,department:x.department,category:x.category,district:x.district,estimated_cost:x.estimated_cost,emd_amount:x.emd_amount,required_documents:docs,minimum_class:val('an_class')||null,min_turnover:num('an_turn')},send_whatsapp:false});
      const a=r.analysis,v=a.eligible===true?[t('eligible'),'ok']:a.eligible===false?[t('notEligible'),'bad']:[t('incomplete'),'warn'];
      const notes=lang==='mr'?a.issues.concat(a.unverified):a.issues_en.concat(a.unverified_en);
      $('#anRes').innerHTML=`<div class="card" style="margin-top:12px"><span class="chip ${v[1]}">${v[0]}</span>
       ${a.missing_documents.length?`<h3>${t('missing')}</h3><ul>${a.missing_documents.map(m=>`<li>${esc(m)}</li>`).join('')}</ul>`:''}
       ${a.matched_documents.length?`<h3>${t('have')}</h3><ul>${a.matched_documents.map(m=>`<li>${esc(m)}</li>`).join('')}</ul>`:''}
       ${notes.map(m=>`<p>⚠️ ${esc(m)}</p>`).join('')}</div>`}
    catch(e){fail('anRes',e)}})}

/* ================= 2. Bid rate ================= */
async function runPredict(btn){if(!needPhone())return;
  const est=num('pr_est');if(!val('pr_cat')||!est){$('#predRes').innerHTML=`<div class="err">${esc(t('needCatEst'))}</div>`;return}
  await busy(btn,async()=>{try{const d=await api('/predict-bid-rate','POST',{phone,tender:{tender_id:'ADHOC',title:val('pr_title')||'Bid rate check',department:val('pr_dept')||'—',category:val('pr_cat'),estimated_cost:est},own_cost_estimate:num('pr_own')});
    const p=d.prediction;
    if(!p.data_available){$('#predRes').innerHTML=`<div class="card empty"><span class="big">🗄️</span><b>${esc(t('noData'))}</b><div>${esc(t('noDataSub',{n:p.samples_found,m:p.minimum_samples_required}))}</div></div>`;return}
    const LBL={aggressive:[t('sAgg'),'agg'],recommended:[t('sRec'),'rec'],conservative:[t('sCon'),'con']};
    const warns=lang==='mr'?p.warnings_mr:p.warnings_en;
    $('#predRes').innerHTML=`<div class="card"><div class="muted">${esc(t('sRec'))}</div><div class="big-rate">${p.predicted_l1_percent>0?'+':''}${p.predicted_l1_percent}%</div><div><b>${esc(descPct(p.predicted_l1_percent))}</b></div>
      <p>${esc(lang==='mr'?p.narrative_mr:p.narrative_en)}</p>
      ${Object.entries(p.scenarios).map(([k,s])=>`<div class="sc ${LBL[k][1]}"><b>${esc(LBL[k][0])}</b><div class="kpi"><div><small>${esc(t('rate'))}</small><b>${s.percent_vs_estimate>0?'+':''}${s.percent_vs_estimate}%</b></div><div><small>${esc(t('bidAmt'))}</small><b>${inr(s.bid_amount)}</b></div>
      ${s.profit_margin_percent!=null?`<div><small>${esc(t('profit'))}</small><b>${inr(s.profit_amount)}</b></div><div><small>${esc(t('margin'))}</small><b>${s.profit_margin_percent}%</b></div>`:''}</div></div>`).join('')}
      ${warns.map(w=>`<div class="err">${esc(w)}</div>`).join('')}
      <p class="muted">${esc(t('basis',{n:p.data_basis.samples,s:p.data_basis.sources.join(', ')}))}</p>
      ${p.frequent_winners.length?`<h3>${esc(t('winners'))}</h3>${p.frequent_winners.map(w=>`<div>${esc(w.name)} — ${w.wins}</div>`).join('')}`:''}</div>`}
  catch(e){fail('predRes',e)}})}

/* ================= 3. Approval ================= */
const STC={PENDING:'warn',CANCELLED:'bad',APPROVED_AWAITING_PORTAL_SUBMISSION:'warn',SUBMITTED:'ok',APPROVED_SUBMISSION_FAILED:'bad'};
async function reqApproval(btn){if(!needPhone())return;
  await busy(btn,async()=>{try{const amt=num('ap_amt');const d=await api('/request-submit-approval','POST',{phone,tender_id:val('ap_id'),tender_title:val('ap_title'),bid_amount:amt,place_call:$('#ap_call').checked});
    const dry=(d.whatsapp&&d.whatsapp.mode==='dry_run')?'<br>'+esc(t('dry')):'';
    $('#apRes').innerHTML=`<div class="info">${esc(t('asked',{a:inr(amt)}))}${dry}</div>`;loadSubs()}catch(e){fail('apRes',e)}})}
async function loadSubs(){
  if(!phone)return;
  try{const d=await api('/submissions?phone='+encodeURIComponent(phone));
    $('#subList').innerHTML=d.submissions.length?d.submissions.map(s=>`<div class="card"><b>${esc(s.tender_title)}</b><div class="muted">${esc(s.tender_ref)} · ${inr(s.bid_amount)}</div>
      <span class="chip ${STC[s.status]||''}">${esc(t('st_'+s.status))}</span>${s.detail&&lang==='mr'?`<p class="muted">${esc(s.detail)}</p>`:''}
      ${s.status==='PENDING'?`<div><button class="btn sm ok" onclick="decide(${s.id},'YES')">${t('yes')}</button><button class="btn sm bad" onclick="decide(${s.id},'NO')">${t('no')}</button></div>`:''}</div>`).join('')
      :`<div class="card empty"><span class="big">📭</span>${esc(t('noSubs'))}</div>`}
  catch(e){fail('subList',e)}}
async function decide(id,decision){
  if(!confirm(decision==='YES'?t('confirmYes'):t('confirmNo')))return;
  try{const r=await api(`/submissions/${id}/decision`,'POST',{phone,decision});toast(lang==='mr'?r.message_mr:r.message_en);loadSubs()}catch(e){toast(e.message)}}

/* ================= 4. Vault ================= */
const VSC={valid:'ok',expiring_soon:'warn',expired:'bad',no_expiry:''};
const STD=[['Aadhaar Card','dt_aadhaar'],['PAN Card','dt_pan'],['GST Registration','dt_gst'],['PWD Registration','dt_pwd'],['Class-1 Certificate','dt_c1'],['EPF Certificate','dt_epf'],['ESIC Certificate','dt_esic'],['Labour Licence','dt_lab'],['Solvency Certificate','dt_sol'],['Turnover Certificate','dt_turn'],['ITR','dt_itr'],['Udyam Registration','dt_udyam'],['DSC','dt_dsc']];
let vaultRows=[];
function docRowHtml(r,i){const d=r.doc;let chip,acts;
  if(!d){chip=`<span class="chip">${esc(t('missingDoc'))}</span>`;acts=`<button onclick="docDialog(${i})">＋ ${esc(t('add'))}</button>`}
  else{chip=`<span class="chip ${d.has_file?(VSC[d.status]||'ok'):'warn'}">${esc(d.has_file?t('vs_'+d.status):t('noFile'))}</span>`;
    acts=(d.has_file?`<button onclick="viewFile(${d.id})">👁</button>`:'')+`<button onclick="docDialog(${i})">⬆</button><button class="dng" onclick="delDoc(${d.id})">🗑</button>`}
  const meta=d?[d.doc_number?t('noLabel',{n:d.doc_number}):'',d.expiry_date?t('expOn',{d:d.expiry_date})+(d.days_left!=null?' ('+t('daysLeft',{n:d.days_left})+')':''):''].filter(Boolean).join(' · '):'';
  return `<div class="row2"><div><b>${esc(r.label)}</b>${meta?`<span class="muted">${esc(meta)}</span><br>`:''}${chip}</div><div class="docacts">${acts}</div></div>`}
async function loadVault(silent){
  if(!loggedIn())return;
  try{const d=await api('/vault/documents');vaultDocs=d.documents;if(silent)return;
    const std=STD.map(([ty,key])=>({ty,label:t(key),doc:d.documents.find(x=>x.doc_type===ty)||null}));
    const extra=d.documents.filter(x=>!STD.some(s=>s[0]===x.doc_type)).map(x=>({ty:x.doc_type,label:x.doc_type,doc:x}));
    vaultRows=std.concat(extra);
    const done=std.filter(r=>r.doc&&r.doc.has_file).length;
    $('#vProg').textContent=t('vProg',{n:done,m:STD.length});$('#vBar').style.width=(done/STD.length*100)+'%';
    $('#vaultList').innerHTML='<div class="card">'+vaultRows.map(docRowHtml).join('')+'</div>'}
  catch(e){if(!silent)fail('vaultList',e)}}
function docDialog(i){
  const r=i>=0?vaultRows[i]:{ty:'',label:'',doc:null};const d=r.doc,aad=r.ty==='Aadhaar Card';
  $('#dlg').innerHTML=`<h2 style="margin-top:0">${esc(r.label||t('addOther'))}</h2>
   ${i<0?`<label>${esc(t('docOther'))}</label><input id="dd_type">`:''}
   ${aad?`<div class="info">${esc(t('aadhaarNote'))}</div>`:`<label>${esc(t('docNo'))}</label><input id="dd_num" value="${esc(d?d.doc_number||'':'')}">`}
   <label>${esc(t('docExp'))}</label><input id="dd_exp" type="date" value="${esc(d&&d.expiry_date||'')}">
   <label>${esc(t('fileLabel'))}</label><input id="dd_file" type="file" accept="image/*,application/pdf">
   <button class="btn" id="dd_go">${esc(t('save'))}</button><button class="btn sec" onclick="$('#dlg').close()">${esc(t('close'))}</button><div id="ddRes"></div>`;
  $('#dlg').showModal();$('#dd_go').onclick=()=>busy($('#dd_go'),()=>saveDoc(r,i,aad))}
async function saveDoc(r,i,aad){
  const f=$('#dd_file').files[0];
  if(f&&f.size>5*1024*1024){$('#ddRes').innerHTML=`<div class="err">${esc(t('e413'))}</div>`;return}
  const type=i<0?val('dd_type'):r.ty;if(!type){$('#ddRes').innerHTML=`<div class="err">${esc(t('needType'))}</div>`;return}
  try{let id=r.doc?r.doc.id:null;const num=aad?null:(val('dd_num')||null),exp=val('dd_exp')||null;
    if(id)await api('/vault/documents/'+id,'PATCH',{doc_number:num,expiry_date:exp});
    else{const c=await api('/vault/documents','POST',{phone,doc_type:type,doc_number:num,expiry_date:exp,file_ref:null});id=c.id}
    if(f){const fd=new FormData();fd.append('file',f);await api('/vault/documents/'+id+'/file','POST',null,fd)}
    $('#dlg').close();toast(t('docAdded'));loadVault()}
  catch(e){fail('ddRes',e);loadVault()}}
async function viewFile(id){
  try{const r=await fetch('/vault/documents/'+id+'/file',{headers:authH(false)});
    if(r.status===401){forceLogin();return}
    if(!r.ok){toast(statusMsg(r.status));return}
    const b=await r.blob(),u=URL.createObjectURL(b),pdf=b.type==='application/pdf';
    $('#dlg').innerHTML=`<h2 style="margin-top:0">${esc(t('viewTitle'))}</h2>${pdf?`<iframe src="${u}" style="width:100%;height:66vh;border:0"></iframe>`:`<img src="${u}" style="width:100%;border-radius:12px">`}
     <a class="btn sec" style="display:block;text-align:center;text-decoration:none" href="${u}" download>${esc(t('download'))}</a><button class="btn sec" onclick="$('#dlg').close()">${esc(t('close'))}</button>`;
    $('#dlg').showModal()}catch(e){toast(e.message)}}
async function delDoc(id){if(!confirm(t('delConfirm')))return;try{await api('/vault/documents/'+id,'DELETE');loadVault()}catch(e){toast(e.message)}}

/* ================= 5. GST ================= */
function addPurchase(){const d=document.createElement('div');d.className='pr';
  d.innerHTML=`<input class="pd" placeholder="${esc(t('purchName'))}"><div class="grid2"><div><label>${t('value')}</label><input class="pv amt" type="number" inputmode="decimal"></div><div><label>GST %</label><input class="pg" type="number" value="18" inputmode="decimal"></div></div>
  <div class="row" style="margin-top:10px"><input type="checkbox" class="pe" checked><span>${t('itcOk')}</span><button class="btn sm sec" style="margin:0 0 0 auto" onclick="this.closest('.pr').remove()">${t('remove')}</button></div>`;
  $('#g_purch').appendChild(d);wireAmounts(d)}
async function runGst(btn){if(!needPhone())return;
  const purchases=[...document.querySelectorAll('#g_purch .pr')].map(r=>({description:r.querySelector('.pd').value.trim()||t('purchDefault'),taxable_value:Number(r.querySelector('.pv').value||0),gst_rate_percent:Number(r.querySelector('.pg').value||0),itc_eligible:r.querySelector('.pe').checked})).filter(p=>p.taxable_value>0);
  await busy(btn,async()=>{try{const d=await api('/get-tax-advice','POST',{phone,taxable_value:num('g_val'),gst_rate_percent:num('g_rate'),intra_state:val('g_intra')==='1',purchases,gst_tds_applicable:$('#g_tds').checked});
    const rows=d.ca_ready_breakdown,pn=r=>lang==='mr'?r.particular:r.particular_en;
    $('#gstRes').innerHTML=`<div class="card"><h3 style="margin-top:0">${t('result')}</h3><p>${esc(lang==='mr'?d.summary_mr:d.summary_en)}</p>
     <div class="kpi"><div><small>${t('outGst')}</small><b>${inr(d.output_tax.total)}</b></div><div><small>${t('eligItc')}</small><b>${inr(d.itc.eligible_total)}</b></div><div><small>${t('netPay')}</small><b>${inr(d.net_gst_payable)}</b></div><div><small>${t('receipt')}</small><b>${inr(d.expected_receipt)}</b></div></div>
     ${rows?`<h3>${t('caDetails')}</h3><table>${rows.map(r=>`<tr><td>${esc(pn(r))}</td><td>${inr(r.amount)}</td></tr>`).join('')}</table>
       <button class="btn sec" id="shareBtn">${t('shareCA')}</button>`:`<div class="pay">${esc(t('draftOnly'))}</div>`}
     <h3>${t('planning')}</h3><ul>${(lang==='mr'?d.strategies_mr:d.strategies_en).map(s=>`<li>${esc(s)}</li>`).join('')}</ul><p class="muted">${esc(lang==='mr'?d.disclaimer_mr:d.disclaimer_en)}</p></div>`;
    if(rows)$('#shareBtn').onclick=()=>{const text='GST (TenderBot AI)\n'+rows.map(r=>`${pn(r).trim()}: ${inr(r.amount)}`).join('\n');
      if(navigator.share)navigator.share({text}).catch(()=>{});else{navigator.clipboard.writeText(text);toast(t('copied'))}}}
  catch(e){fail('gstRes',e)}})}

/* ================= AI chat ================= */
let chatHist=[];
const fmt=x=>esc(x).replace(/\*\*(.+?)\*\*/g,'<b>$1</b>').replace(/\n/g,'<br>');
function drawChat(typing){
  $('#chatLog').innerHTML=`<div class="msg bot">${fmt(t('chatHello'))}</div>`+chatHist.map(m=>`<div class="msg ${m.role==='user'?'me':'bot'}">${fmt(m.content)}</div>`).join('')+(typing?'<div class="msg bot">…</div>':'');
  const l=$('#chatLog');l.scrollTop=l.scrollHeight}
function renderChips(){$('#chatChips').innerHTML=['chip1','chip2','chip3'].map(k=>`<button onclick="sendChat(t('${k}'))">${esc(t(k))}</button>`).join('')}
function openChat(){$('#chatDlg').showModal();drawChat();renderChips();$('#chatIn').placeholder=t('chatPh')}
async function sendChat(text){
  text=(text||$('#chatIn').value).trim();if(!text)return;$('#chatIn').value='';
  const hist=chatHist.filter(m=>!m.err).slice(-10).map(m=>({role:m.role,content:m.content}));
  chatHist.push({role:'user',content:text});drawChat(true);
  try{const d=await api('/chat','POST',{phone,message:text,history:hist,language:lang});chatHist.push({role:'assistant',content:d.reply})}
  catch(e){chatHist.push({role:'assistant',content:'⚠️ '+e.message,err:true})}
  drawChat()}

/* ================= start ================= */
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
wireAmounts();addPurchase();applyLang();
if(loggedIn()){api('/me').then(d=>{profile=profFrom(d);saveLocal();applyLang()}).catch(()=>{});go('home')}
else{if(phone)$('#w_phone').value=phone;go('welcome')}
</script></body></html>
"""
