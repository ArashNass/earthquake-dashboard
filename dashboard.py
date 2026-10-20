# dashboard.py - Builds the HTML dashboard from event data.
# The client-side JS lives in dashboard_js.js (single source of truth) and is
# read at build time; data is injected via __PLACEHOLDER__ tokens.

import html
import json
from pathlib import Path

from datetime import datetime, timezone

from settings import ALERT_C, MMI_C, MMI_SCALE, PAGER_THRESHOLDS, JS_FILE

HERE = Path(__file__).resolve().parent

ERCC_UPGRADE_JS = r"""
(function(){
  // Global alerts from three free, keyless feeds: USGS (significant earthquakes), UN GDACS (alerts of every
  // hazard type, with RED / ORANGE / GREEN levels) and NASA EONET (open storms, volcanoes, floods, wildfires ...).
  // Items are grouped by hazard, capped per hazard, ordered by severity and interleaved so the ticker always mixes types.
  var DAY = 864e5;
  var COLORS = {'Earthquake':'#d9534f','Tropical Cyclone':'#5b7fd6','Severe Storm':'#5b7fd6','Flood':'#1976d2','Volcano':'#ef6c00','Wildfire':'#e65100','Drought':'#b08900','Landslide':'#8d6e63','Sea and Lake Ice':'#4aa3c8','Snow':'#6aa5c8','Dust and Haze':'#a1887f','Temperature Extreme':'#c62828','Water Color':'#26a69a','Manmade':'#7e57c2'};
  var CAP = {'Earthquake':5,'Tropical Cyclone':3,'Severe Storm':3,'Flood':4,'Volcano':3,'Wildfire':4,'Drought':2};
  var EONET_CAT = {'Severe Storms':'Severe Storm','Volcanoes':'Volcano','Wildfires':'Wildfire','Floods':'Flood','Landslides':'Landslide','Drought':'Drought','Temperature Extremes':'Temperature Extreme','Earthquakes':'Earthquake'};
  var GD_CAT = {TC:'Tropical Cyclone', FL:'Flood', VO:'Volcano', DR:'Drought', WF:'Wildfire'};

  function esc(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
  function safeUrl(u){ try { var x = new URL(u); return (x.protocol === 'https:' || x.protocol === 'http:') ? x.href : ''; } catch(e){ return ''; } }
  function iso(ms){ return new Date(ms).toISOString().slice(0,10); }
  function lvlOf(x){ x = (x || '').toLowerCase(); return x === 'red' ? 3 : x === 'orange' ? 2 : x === 'yellow' ? 1 : 0; }
  function getJson(url, name){
    var c = new AbortController(), t = setTimeout(function(){ c.abort(); }, 9000);
    return fetch(url, { signal: c.signal }).then(function(r){
      clearTimeout(t); console.log('[disaster-alerts]', name, 'status', r.status);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.text();
    }).then(function(txt){ return txt && txt.trim() ? JSON.parse(txt) : null; })
      .catch(function(e){ clearTimeout(t); console.log('[disaster-alerts]', name, 'failed:', e.message || e); return null; });
  }
  function tidy(name, re, country){
    var t = (name || '').replace(re, '').replace(/\s+/g, ' ').replace(/^[\s:\u2013\u2014-]+/, '').trim();
    if (country && t && country.length < 34 && t.toLowerCase().indexOf(country.toLowerCase()) < 0 && country.toLowerCase().indexOf(t.toLowerCase()) < 0) t += ' (' + country + ')';
    return t || country || name;
  }
  function buildAlerts(r){
    var now = Date.now(), pool = [], gdTC = [];
    ((r[0] && r[0].features) || []).forEach(function(f){            // USGS
      var p = f.properties || {}, u = safeUrl(p.url), t = (p.title || p.place || '').trim();
      if (u && t) pool.push({ cat:'Earthquake', title:t, link:u, lvl: lvlOf(p.alert) >= 2 ? lvlOf(p.alert) : 0, t:p.time || 0, m:p.mag || 0 });
    });
    [r[1], r[2]].forEach(function(d){                                // GDACS
      ((d && d.features) || []).forEach(function(f){
        var p = f.properties || {}, cat = GD_CAT[p.eventtype];
        if (!cat || String(p.iscurrent) === 'false') return;
        var t = Date.parse(p.fromdate + 'Z') || 0;
        if (cat === 'Drought' && now - t > 60 * DAY) return;
        if (cat === 'Wildfire' && lvlOf(p.alertlevel) < 2) return;
        var u = safeUrl((p.url && p.url.report) || '');
        var txt = tidy(p.name, /^(tropical cyclone|flood|eruption|volcano|drought|(wild|forest)\s?fire)\s*(in|:)?\s*/i, (p.country || '').trim());
        if (!u || !txt) return;
        if (cat === 'Tropical Cyclone') gdTC.push((p.name || '').toLowerCase());
        pool.push({ cat:cat, title:txt, link:u, lvl:lvlOf(p.alertlevel), t:t, m:0 });
      });
    });
    ((r[3] && r[3].events) || []).forEach(function(e){               // NASA EONET
      var raw = (e.categories && e.categories[0] && e.categories[0].title) || 'Event', cat = EONET_CAT[raw] || raw;
      var u = safeUrl(e.link || (e.sources && e.sources[0] && e.sources[0].url)), t = (e.title || '').trim();
      if (!u || !t || cat === 'Earthquake' || /prescribed/i.test(t)) return;   // controlled burns are not alerts
      var last = (e.geometry && e.geometry.length && e.geometry[e.geometry.length - 1].date) || '';
      if (cat === 'Severe Storm'){                                    // skip storms GDACS already reports (it carries the alert level)
        var nm = t.split(/\s+/).pop().toLowerCase();
        if (nm.length > 3 && gdTC.some(function(g){ return g.indexOf(nm) >= 0; })) return;
      }
      var re = new RegExp('^' + cat.replace(/ /g, '\\s*') + 's?\\s*', 'i');
      pool.push({ cat:cat, title:t.replace(re, '') || t, link:u, lvl:0, t:Date.parse(last) || 0, m:0 });
    });
    var groups = {};
    pool.forEach(function(i){ (groups[i.cat] = groups[i.cat] || []).push(i); });
    var cats = Object.keys(groups);
    cats.forEach(function(c){
      groups[c].sort(function(a, b){ return b.lvl - a.lvl || b.m - a.m || b.t - a.t; });
      groups[c] = groups[c].slice(0, CAP[c] || 2);
    });
    cats.sort(function(a, b){ return groups[b][0].lvl - groups[a][0].lvl || groups[b].length - groups[a].length; });
    var out = [], more = true, i = 0;
    while (more && out.length < 30){ more = false; cats.forEach(function(c){ if (groups[c][i]){ out.push(groups[c][i]); more = true; } }); i++; }
    return out;
  }

  var G = 'https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH?', to = iso(Date.now() + DAY);
  Promise.all([
    getJson('https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson', 'USGS'),
    getJson(G + 'eventlist=TC;FL;VO;DR;WF&alertlevel=Orange;Red&fromdate=' + iso(Date.now() - 21 * DAY) + '&todate=' + to, 'GDACS serious'),
    getJson(G + 'eventlist=TC;FL;VO&alertlevel=Green&fromdate=' + iso(Date.now() - 7 * DAY) + '&todate=' + to, 'GDACS recent'),
    getJson('https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=30', 'EONET')
  ]).then(function(results){
    var allItems = buildAlerts(results);
    console.log('[disaster-alerts] combined items:', allItems.length);

    var scroll = document.getElementById('ea-scroll');
    var track = scroll ? scroll.parentElement : null;
    var bar = document.getElementById('ea-bar');
    var filterEl = document.getElementById('ea-filter');
    var prevBtn = document.getElementById('ea-prev');
    var nextBtn = document.getElementById('ea-next');
    var playBtn = document.getElementById('ea-play');
    if (!scroll || !bar || !track) { console.log('[disaster-alerts] DOM elements not found'); return; }

    if (!allItems.length) {
      console.log('[disaster-alerts] no items from either source');
      scroll.innerHTML = '<span class="ea-item" style="cursor:default;color:#b91c1c">No live alerts available right now</span>';
      if (filterEl) filterEl.style.display = 'none';
      return;
    }

    var ICON_PAUSE = '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>';
    var ICON_PLAY  = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>';

    // The ticker moves by translating .ea-scroll inside a clipped (overflow:hidden) track,
    // so there is no scrollable element and therefore no scrollbar or manual horizontal scroller.
    var items = allItems, paused = false, hover = false, raf = null, last = 0;
    var offset = 0, target = null;
    var SPEED = 30; // px per second
    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    var STORMS = {'Tropical Cyclone':1, 'Severe Storm':1}, MAIN = {'Earthquake':1,'Tropical Cyclone':1,'Severe Storm':1,'Flood':1,'Volcano':1,'Wildfire':1};
    function matches(it, f){
      if (!f || f === 'all') return true;
      if (f === 'serious') return it.lvl >= 2;
      if (f === 'storm') return !!STORMS[it.cat];
      if (f === 'other') return !MAIN[it.cat];
      return it.cat === f;
    }
    if (filterEl){                                   // only offer filters that currently have alerts
      Array.prototype.slice.call(filterEl.options).forEach(function(o){
        if (o.value !== 'all' && !allItems.some(function(it){ return matches(it, o.value); })) o.parentNode.removeChild(o);
      });
    }

    function render(filter){
      items = allItems.filter(function(it){ return matches(it, filter); });
      offset = 0; target = null;
      scroll.style.transform = 'translate3d(0,0,0)';
      if (!items.length){
        scroll.innerHTML = '<span class="ea-item" style="cursor:default">No events for this filter</span>';
        return;
      }
      var chips = items.map(function(it){
        var lv = it.lvl >= 3 ? '<span class="ea-lvl red">RED</span>' : it.lvl === 2 ? '<span class="ea-lvl orange">ORANGE</span>' : '';
        return '<a class="ea-item" href="' + esc(it.link) + '" target="_blank" rel="noopener"><span class="ea-cat" style="--ac:' + (COLORS[it.cat] || '#6b7385') + '">' + esc(it.cat) + '</span>' + lv + esc(it.title) + '</a><span class="ea-sep">&#8226;</span>';
      }).join('');
      // Duplicated once so the loop point (wrapping at the halfway mark) is seamless.
      scroll.innerHTML = chips + chips;
    }

    function updateNavState(){
      var enabled = items.length > 1;
      [prevBtn, nextBtn, playBtn].forEach(function(b){ if (b) b.disabled = !enabled; });
    }

    function tick(ts){
      var dt = last ? Math.min(ts - last, 100) / 1000 : 0;
      last = ts;
      if (items.length > 1){
        if (target !== null){
          offset += (target - offset) * 0.16;
          if (Math.abs(target - offset) < 0.5){ offset = target; target = null; }
        } else if (!paused && !hover){
          offset += SPEED * dt;
        }
        var half = scroll.scrollWidth / 2;
        if (half > 0){
          var wrapped = ((offset % half) + half) % half;
          if (target !== null) target += wrapped - offset;
          offset = wrapped;
        }
        scroll.style.transform = 'translate3d(' + (-offset).toFixed(2) + 'px,0,0)';
      }
      raf = requestAnimationFrame(tick);
    }

    function setPaused(p){
      paused = p;
      if (playBtn){
        playBtn.innerHTML = paused ? ICON_PLAY : ICON_PAUSE;
        playBtn.title = paused ? 'Play' : 'Pause';
        playBtn.setAttribute('aria-label', paused ? 'Play' : 'Pause');
      }
    }

    function nudge(dir){
      target = offset + dir * Math.max(220, track.clientWidth * 0.7);
    }

    if (prevBtn) prevBtn.addEventListener('click', function(){ nudge(-1); });
    if (nextBtn) nextBtn.addEventListener('click', function(){ nudge(1); });
    if (playBtn) playBtn.addEventListener('click', function(){ setPaused(!paused); });
    // hold still while the pointer is over the ticker or a link has keyboard focus, so alerts are readable and clickable
    track.addEventListener('pointerenter', function(e){ if (e.pointerType === 'mouse') hover = true; });
    track.addEventListener('pointerleave', function(){ hover = false; });
    track.addEventListener('focusin', function(){ hover = true; });
    track.addEventListener('focusout', function(){ hover = false; });

    if (filterEl) filterEl.addEventListener('change', function(){
      render(this.value);
      updateNavState();
    });

    render('all');
    updateNavState();
    setPaused(!!reduceMotion); // moving by default; static if the visitor prefers reduced motion
    raf = requestAnimationFrame(tick);
    console.log('[disaster-alerts] banner shown with', allItems.length, 'items');
  });
})();
"""



def _age_text(t_ms):
    """'37h ago' / '5d ago'. The page refreshes this in the browser, so it never goes stale."""
    if not t_ms:
        return ""
    h = (datetime.now(timezone.utc).timestamp() * 1000 - t_ms) / 3.6e6
    if h < 1:
        return "just now"
    return f"{int(h)}h ago" if h < 48 else f"{int(h / 24)}d ago"


def sidebar_item(e, selected):
    ac  = ALERT_C.get(e.get("alert") or "", ALERT_C[""])
    sel = "background:#e8f0fe;border-left:3px solid #1565c0;" if selected else "border-left:3px solid transparent;"
    dot = "#2e7d32" if e.get("has_shakemap") else "#ccc"
    place = e.get("place") or "Unknown location"
    pl  = html.escape(place[:44] + ("..." if len(place) > 44 else ""))
    mag = round(float(e.get("mag") or 0), 1)
    alert = html.escape(e.get("alert") or "PENDING")
    t_ms = int(e.get("t_ms") or 0)
    # Click handling is done via event delegation in JS; only data-id is needed.
    return (
        '<div class="ev-item' + (' ev-sel' if selected else '') + '" data-track-action="select_event" data-id="' + html.escape(e["id"], quote=True) + '" '
        'style="' + sel + 'cursor:pointer;padding:10px 14px;border-bottom:1px solid #eee;">'
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:2px">'
        '<span style="font-size:18px;font-weight:900;color:' + ac + '">M' + str(mag) + '</span>'
        '<span style="display:flex;align-items:center;gap:5px" title="USGS PAGER alert level">'
        '<span style="font-size:9px;font-weight:700;color:' + ac + ';text-transform:uppercase">' + alert + '</span>'
        '<span style="width:7px;height:7px;border-radius:50%;background:' + dot + ';display:inline-block"></span>'
        '</span></div>'
        '<div style="font-size:11px;font-weight:600;color:#1a1f36;margin-bottom:2px" title="' + html.escape(place, quote=True) + '">' + pl + '</div>'
        '<div style="font-size:10px;color:#888"><span class="ev-age" data-t="' + str(t_ms) + '">' + html.escape(_age_text(t_ms)) + '</span> - '
        + str(round(float(e.get("depth") or 0))) + ' km deep</div>'
        '</div>'
    )

# ── Serialise event data for JSON embedding ───────────────────────────────────

_EV_KEYS_DEFAULTS = {
    "event_id": "", "mag": 0, "mag_type": "", "place": "", "lat": 0, "lon": 0, "depth": 0,
    "depth_note": "", "t_str": "", "t_ms": 0, "t_iso": "", "alert_color": ALERT_C[""],
    "pager_alert": "", "status": "", "mmi": 0, "mmi_roman": "", "mmi_shaking": "", "mmi_damage": "",
    "mmi_color": "#ccc", "felt": 0, "cdi": None, "tsunami": False, "energy_mt": 0, "rupture_km": 0, "url": "",
}

_DATA_KEYS = ("aftershock", "focal", "finite_fault", "origin", "pager", "ground_failure", "summary",
              "weather", "narrative")


def serialize(data):
    ev = data.get("ev") or {}
    sm = data.get("sm") or {}
    out = {
        "ev":         {k: ev.get(k, dflt) for k, dflt in _EV_KEYS_DEFAULTS.items()},
        "sm":         {"mmi_url": sm.get("mmi_url", ""), "pga_url": sm.get("pga_url", ""),
                       "peak": sm.get("peak"), "version": sm.get("version"),
                       "status": sm.get("status"), "processed": sm.get("processed")},
        "historical": data.get("historical") or [],
        "general":    data.get("general") or [],
        "media":      data.get("media") or [],
        "data_unavailable": bool(data.get("data_unavailable")),
    }
    for k in _DATA_KEYS:
        out[k] = data.get(k)
    return out


def _json_for_script(obj):
    """JSON that is safe to embed inside a <script> element."""
    return (json.dumps(obj, ensure_ascii=False)
            .replace("<", "\\u003c")
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))

SENTINEL_LOADER = r"""<script>
/* SENTINEL theme loader. Adds a small "Theme: Standard | Sentinel" switch to the page. The theme files
   (/sentinel/) are only fetched when Sentinel is chosen (or was chosen last time). ?theme=sentinel / ?theme=off
   also work as links. Keep this copy in sync with the pages. */
(function(){
  var K='sx-theme',B='/sentinel/',V='7',d=document,w=window,loading=0,pending=null;
  function g(k){try{return localStorage.getItem(k)}catch(e){return null}}
  function s(k,v){try{localStorage.setItem(k,v)}catch(e){}}
  if(/[?&]theme=sentinel(&|$)/.test(location.search))s(K,'sentinel');
  if(/[?&]theme=off(&|$)/.test(location.search))s(K,'off');
  function load(mode){
    pending=mode;
    if(w.Sentinel){w.Sentinel.start(mode);return}
    if(loading)return; loading=1;
    var l=d.createElement('link');l.rel='stylesheet';l.href=B+'sentinel.css?v='+V;d.head.appendChild(l);
    var j=d.createElement('script');j.src=B+'sentinel.js?v='+V;j.onload=function(){if(w.Sentinel)w.Sentinel.start(pending)};
    j.onerror=function(){loading=0};d.head.appendChild(j);
  }
  if(g(K)==='sentinel'){
    var st=d.createElement('style');st.id='sx-pre';st.textContent='html{background:#01040a}body{opacity:0}';d.head.appendChild(st);
    setTimeout(function(){var e=d.getElementById('sx-pre');if(e&&e.parentNode)e.parentNode.removeChild(e)},2500);
    load('resume');
  }
  var css=d.createElement('style');
  css.textContent='#sx-switch{position:fixed;left:14px;bottom:14px;z-index:99991;display:flex;align-items:center;gap:2px;padding:3px;border-radius:999px;background:rgba(12,18,32,.9);border:1px solid rgba(138,242,255,.35);box-shadow:0 4px 18px rgba(0,0,0,.35);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px);font:700 12px/1 system-ui,-apple-system,"Segoe UI",sans-serif}'
   +'#sx-switch.sx-quake{bottom:54px}'
   +'#sx-switch span{padding:0 8px 0 10px;color:#9fb3c8;font-weight:600;letter-spacing:.04em}'
   +'#sx-switch button{appearance:none;-webkit-appearance:none;border:0;margin:0;cursor:pointer;min-height:30px;padding:0 13px;border-radius:999px;background:transparent;color:#c9d6e3;font:inherit;letter-spacing:.03em;transition:background .15s,color .15s}'
   +'#sx-switch button:hover{color:#fff}'
   +'#sx-switch button:focus-visible{outline:2px solid #8af2ff;outline-offset:1px}'
   +'#sx-switch button[aria-pressed=true]{background:#fff;color:#0c1220}'
   +'#sx-switch button[data-t=sentinel][aria-pressed=true]{background:rgba(56,213,255,.22);color:#8af2ff;box-shadow:0 0 14px rgba(56,213,255,.45)}'
   +'@media(max-width:420px){#sx-switch span{display:none}#sx-switch button{padding:0 12px}}'
   +'@media print{#sx-switch{display:none}}';
  d.head.appendChild(css);
  function build(){
    if(d.getElementById('sx-switch'))return;
    var box=d.createElement('div');box.id='sx-switch';box.setAttribute('role','group');box.setAttribute('aria-label','Page theme');
    if(/earthquake-dashboard/.test(location.pathname))box.className='sx-quake';
    box.innerHTML='<span>Theme</span><button type="button" data-t="std">Standard</button><button type="button" data-t="sentinel" title="Mission-control theme">Sentinel</button>';
    function sync(){
      var on=d.documentElement.classList.contains('sx');
      box.querySelector('[data-t=std]').setAttribute('aria-pressed',on?'false':'true');
      box.querySelector('[data-t=sentinel]').setAttribute('aria-pressed',on?'true':'false');
    }
    box.addEventListener('click',function(e){
      var b=e.target.closest&&e.target.closest('button');if(!b)return;
      if(b.getAttribute('data-t')==='sentinel'){if(d.documentElement.classList.contains('sx'))return;load('engage')}
      else if(w.Sentinel){w.Sentinel.disengage(true)}else{s(K,'off')}
      setTimeout(sync,0);
    });
    new MutationObserver(sync).observe(d.documentElement,{attributes:true,attributeFilter:['class']});
    sync();d.body.appendChild(box);
  }
  if(d.readyState==='loading')d.addEventListener('DOMContentLoaded',build);else build();
})();
</script>
"""

# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """\
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#f4f6fb;font-size:13px;color:#1a1f36}
.app-shell{display:flex;flex-direction:column;height:100vh;overflow:hidden}
.nav{display:flex;justify-content:space-between;align-items:center;background:#fff;border-bottom:1px solid #e2e6f0;padding:11px 20px;flex-shrink:0;box-shadow:0 1px 6px rgba(0,0,0,.06)}
.nav-title{font-size:15px;font-weight:700}.nav-sub{font-size:11px;color:#64748b}
.ea-bar{display:none;align-items:center;gap:10px;background:#fef2f2;border-top:1px solid #fecaca;border-bottom:1px solid #fecaca;padding:11px 22px;flex-shrink:0;overflow:hidden;margin-top:14px}
.ea-bar.ea-show{display:flex}
.ea-label{display:flex;align-items:center;gap:7px;font-size:12px;font-weight:800;letter-spacing:.8px;color:#fff;white-space:nowrap;flex-shrink:0;background:#dc2626;padding:5px 12px;border-radius:4px}
.ea-dot{width:7px;height:7px;border-radius:50%;background:#fff;flex-shrink:0;animation:pulse 2s infinite}
.ea-controls{display:flex;align-items:center;gap:6px;flex-shrink:0}
.ea-nav,.ea-play{flex-shrink:0;width:24px;height:24px;border-radius:50%;border:1px solid #fca5a5;background:#fff;color:#b91c1c;cursor:pointer;display:flex;align-items:center;justify-content:center;padding:0;transition:.15s}
.ea-nav svg,.ea-play svg{width:13px;height:13px;display:block}
.ea-nav:hover,.ea-play:hover{background:#dc2626;border-color:#dc2626;color:#fff}
.ea-nav:disabled,.ea-play:disabled{opacity:.3;cursor:default;pointer-events:none}
.ea-track{flex:1;min-width:0;overflow:hidden;white-space:nowrap}
.ea-scroll{display:inline-block;white-space:nowrap;will-change:transform}
.ea-item{color:#7f1d1d;text-decoration:none;font-size:14px;font-weight:600;padding:0 4px}
.ea-item:hover{color:#dc2626;text-decoration:underline}
.ea-sep{color:#e6a5a5;margin:0 26px;font-size:12px}
.ea-cat{font-size:10.5px;font-weight:800;letter-spacing:.05em;text-transform:uppercase;color:var(--ac,#7f1d1d);margin-right:7px}
.ea-lvl{display:inline-block;font-size:9.5px;font-weight:800;letter-spacing:.07em;padding:2px 6px;border-radius:5px;line-height:1.3;color:#fff;margin-right:7px;vertical-align:1px}
.ea-lvl.red{background:#c62828}
.ea-lvl.orange{background:#b45309}
html.sx .ea-cat{color:color-mix(in srgb,var(--ac,#ff8fa3) 55%,#fff)}
.ea-more{flex-shrink:0;color:#b91c1c;font-size:10.5px;font-weight:700;text-decoration:none;white-space:nowrap}
.ea-more:hover{color:#7f1d1d}
.ea-filter{flex-shrink:0;background:#fff;color:#7f1d1d;border:1px solid #fca5a5;border-radius:5px;font-size:11px;font-weight:700;padding:5px 9px;cursor:pointer}
.ea-filter:hover{border-color:#dc2626}
.ea-filter option{background:#fff;color:#7f1d1d}
@media(max-width:680px){.ea-filter{font-size:9px;padding:3px 6px}.ea-item{font-size:12px}.ea-label{font-size:10px;padding:4px 8px}
  .ea-bar{flex-wrap:wrap;padding:10px 14px;gap:8px}
  .ea-label{order:1}
  .ea-filter{order:2;margin-left:auto;max-width:140px}
  .ea-controls{order:3}
  .ea-track{order:4;flex:1 1 100%;min-width:0}}
.live{width:8px;height:8px;border-radius:50%;background:#2e7d32;display:inline-block;margin-right:7px;animation:pulse 2s infinite;vertical-align:middle}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.body{display:flex;flex:1;overflow:hidden;min-height:0}
.sidebar{width:272px;flex-shrink:0;background:#fff;border-right:1px solid #e2e6f0;display:flex;flex-direction:column;overflow:hidden}
.sb-hdr{padding:10px 14px;border-bottom:1px solid #e2e6f0;background:#f8f9fc;flex-shrink:0}
.sb-title{font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1px}
.sb-legend{display:flex;gap:14px;font-size:10px;color:#888;padding:6px 14px;border-bottom:1px solid #e2e6f0;flex-shrink:0}
.sb-list{overflow-y:auto;flex:1}.ev-item:hover{background:#f0f4ff!important}
.rp{flex:1;overflow-y:auto;background:#f4f6fb}
#rp-inner{padding:16px;max-width:1060px;margin:0 auto}
@media(max-width:760px){
  body{overflow:auto;height:auto}
  .app-shell{height:auto;min-height:100vh;overflow:visible}
  .body{flex-direction:column;flex:none;overflow:visible}
  .sidebar{width:100%;border-right:none;border-bottom:1px solid #e2e6f0}
  .sb-list{display:flex;overflow-x:auto;overflow-y:hidden}
  .ev-item{min-width:200px;border-right:1px solid #eee}
  .rp{overflow:visible}
  #leaflet-map{height:340px!important}
  /* the three headline numbers share one row instead of three tall cards */
  .mbox-row{grid-template-columns:repeat(3,minmax(0,1fr))!important;gap:6px!important}
  .mbox{padding:9px 4px!important;border-radius:8px!important}
  .mbox-l{font-size:8px!important;letter-spacing:.3px!important;margin-bottom:4px!important;overflow-wrap:anywhere}
  .mbox-v{font-size:20px!important}
  .mbox-s{font-size:9.5px!important;margin-top:3px!important;line-height:1.25;overflow-wrap:anywhere}
  /* smaller magnitude; it sits beside the place name when there is room, otherwise above it */
  .hero-card{padding:16px!important}
  .hero-row{gap:4px 8px!important;margin-bottom:12px!important}
  .hero-mag{font-size:54px!important;letter-spacing:-1.5px!important}
  .hero-main{min-width:150px!important}
  /* badge + alert text stay on one line; if a screen is too narrow they wrap as a pair, never mid-sentence */
  .hero-alert{display:flex;flex-wrap:wrap;align-items:center;gap:4px 6px}
  .hero-badge{font-size:10px!important;padding:3px 9px!important}
  .hero-pager{font-size:10px!important;margin-left:0!important;white-space:nowrap}
}
"""

# ── Build HTML ────────────────────────────────────────────────────────────────

def load_js():
    path = HERE / JS_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"{JS_FILE} not found next to dashboard.py - it is required to build the dashboard.")
    return path.read_text(encoding="utf-8")


def build(top_events, all_data, now_str):
    # all_data[i] was loaded from top_events[i]; keep the two lists aligned and
    # make the sidebar use the id the data was actually stored under, so a
    # feed-id/code mismatch can never break event selection.
    pairs = [(e, d) for e, d in zip(top_events, all_data) if d and d.get("ev")]
    top_events = [dict(e, id=d["ev"]["event_id"]) for e, d in pairs]
    all_data   = [d for _, d in pairs]

    first_id = all_data[0]["ev"]["event_id"] if all_data else ""
    sb       = "".join(sidebar_item(e, e.get("id") == first_id) for e in top_events)

    js = (load_js()
          .replace("__ALL_DATA__",   _json_for_script([serialize(d) for d in all_data]))
          .replace("__FIRST_ID__",   _json_for_script(first_id))
          .replace("__MMI_COLORS__", _json_for_script(MMI_C))
          .replace("__MMI_SCALE__", _json_for_script({str(k): list(v) for k, v in MMI_SCALE.items()}))
          .replace("__ALERT_C__",    _json_for_script(ALERT_C))
          .replace("__PAGER_THRESHOLDS__", _json_for_script(PAGER_THRESHOLDS)))

    return "\n".join([
        "<!DOCTYPE html>",
        '<html lang="en"><head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        SENTINEL_LOADER,
        '<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%20viewBox%3D%270%200%2024%2024%27%3E%3Crect%20width%3D%2724%27%20height%3D%2724%27%20rx%3D%275%27%20fill%3D%27%230f2350%27%2F%3E%3Cpath%20d%3D%27M3%2012h4l2.5-7%205%2014%202.5-7h4%27%20fill%3D%27none%27%20stroke%3D%27white%27%20stroke-width%3D%271.9%27%20stroke-linecap%3D%27round%27%20stroke-linejoin%3D%27round%27%2F%3E%3C%2Fsvg%3E">',
        "<title>Live Earthquake Dashboard - ShakeMaps &amp; Aftershocks | Arash Nassirpour</title>",
        '<meta name="description" content="Track major earthquakes with live USGS data, ShakeMaps, aftershock forecasts, fault mechanisms, PAGER impact estimates and global disaster alerts." />',
        '<link rel="canonical" href="https://arashnassirpour.com/earthquake-dashboard/" />',
        '<meta property="og:title" content="Live Earthquake Dashboard - ShakeMaps &amp; Aftershocks" />',
        '<meta property="og:description" content="Track major earthquakes with live USGS data, ShakeMaps, aftershock forecasts, fault mechanisms and PAGER impact estimates." />',
        '<meta property="og:url" content="https://arashnassirpour.com/earthquake-dashboard/" />',
        '<meta property="og:type" content="website" />',
        '<meta property="og:site_name" content="Arash Nassirpour" />',
        '<meta property="og:image" content="https://arashnassirpour.com/earthquake-dashboard/og-image.png" />',
        '<meta name="author" content="Arash Nassirpour" />',
        '<meta name="robots" content="index, follow, max-image-preview:large" />',
        '<meta name="twitter:card" content="summary_large_image" />',
        '<meta name="twitter:title" content="Live Earthquake Dashboard - ShakeMaps &amp; Aftershocks" />',
        '<meta name="twitter:description" content="Track major earthquakes with live USGS data, ShakeMaps, aftershock forecasts and PAGER impact estimates." />',
        '<meta name="twitter:image" content="https://arashnassirpour.com/earthquake-dashboard/og-image.png" />',
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"SoftwareApplication","name":"Rapid Earthquake Response",'
        '"applicationCategory":"EngineeringApplication","operatingSystem":"Web",'
        '"url":"https://arashnassirpour.com/earthquake-dashboard/",'
        '"description":"Live USGS earthquake briefing with ShakeMaps, aftershock forecasts, and a global disaster alerts ticker.",'
        '"offers":{"@type":"Offer","price":"0","priceCurrency":"USD"},'
        '"author":{"@type":"Person","name":"Arash Nassirpour"}}'
        '</script>',
        '<script defer src="/assets/analytics.js?v=2"></script>',
        '\n<script defer src="/assets/engagement.js?v=1"></script>\n<script type="module" src="/assets/vitals.js?v=1"></script>\n<link rel="stylesheet" href="/assets/tool-guide.css?v=1">\n',
        '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>',
        "<style>" + CSS + "</style>",
        "</head><body>",
        '<div class="app-shell">',
        # Shared site header - keep identical across all arashnassirpour.com repos.
        """<!-- shared site header -->
<header class="site-hd"><style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
.site-hd{background:#0f2350;border-bottom:1px solid rgba(255,255,255,.08);font-family:Inter,'Segoe UI',system-ui,sans-serif;flex-shrink:0;position:sticky;top:0;z-index:9999;box-shadow:0 4px 20px rgba(6,14,36,.18)}
.site-hd::after{content:'';position:absolute;left:0;right:0;bottom:-1px;height:1px;background:linear-gradient(90deg,transparent,rgba(124,157,255,.55),transparent)}
.site-hd .hd-in{max-width:1080px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;padding:14px 24px}
.site-hd a{text-decoration:none;color:#fff;font-size:12.5px;font-weight:500;transition:opacity .15s;opacity:.9}
.site-hd a:hover{opacity:1}
.site-hd .hd-home{color:#fff;font-size:13.5px;font-weight:600;opacity:1}
.site-hd .hd-links{display:flex;align-items:center;gap:16px}
.site-hd .hd-dd{position:relative}
.site-hd .hd-dd-btn{display:flex;align-items:center;gap:6px;background:none;border:none;cursor:pointer;font:500 12.5px Inter,'Segoe UI',system-ui,sans-serif;color:#fff;padding:6px 2px;transition:opacity .15s;opacity:.9}
.site-hd .hd-dd-btn:hover,.site-hd .hd-dd.open .hd-dd-btn{opacity:1}
.site-hd .hd-dd-btn.hd-on-btn{color:#9fc0ff;opacity:1}
.site-hd .hd-dd-btn-ic{width:15px;height:15px;flex-shrink:0}
.site-hd .hd-dd-btn-ic svg{width:100%;height:100%}
.site-hd .hd-dd-btn svg.hd-chev{width:10px;height:10px;transition:transform .15s;flex-shrink:0;color:#fff}
.site-hd .hd-dd.open .hd-dd-btn svg.hd-chev{transform:rotate(180deg)}
.site-hd .hd-dd-menu{position:fixed;background:#1f3d78;border:1px solid rgba(255,255,255,.12);border-radius:12px;box-shadow:0 16px 40px rgba(0,0,0,.4);width:432px;max-width:calc(100vw - 28px);max-height:calc(100vh - 84px);overflow-y:auto;overscroll-behavior:contain;-webkit-overflow-scrolling:touch;padding:8px;display:none;grid-template-columns:repeat(3,1fr);gap:3px;align-content:start;z-index:10000}
.site-hd .hd-dd.open .hd-dd-menu{display:grid}
.site-hd .hd-dd-menu a{min-width:0;display:flex;flex-direction:row;align-items:center;gap:9px;padding:9px 12px;border-radius:8px;font-size:12px;color:#fff;font-weight:500;text-align:left;line-height:1.25;opacity:.92;height:66px;box-sizing:border-box}.site-hd .hd-dd-menu a .hd-dd-lbl{flex:1;min-width:0;white-space:normal;overflow-wrap:anywhere}.site-hd .hd-dd-cat{grid-column:1/-1;font-size:10px;font-weight:700;letter-spacing:.07em;text-transform:uppercase;color:rgba(255,255,255,.5);padding:10px 10px 4px;margin-top:6px;border-top:1px solid rgba(255,255,255,.12)}.site-hd .hd-dd-cat:first-child{margin-top:0;padding-top:2px;border-top:0}
.site-hd .hd-dd-menu a:hover{background:rgba(255,255,255,.1);opacity:1}
.site-hd .hd-dd-menu a.hd-on{background:rgba(255,255,255,.16);opacity:1}
.site-hd .hd-dd-menu a .hd-dd-ic{width:17px;height:17px;flex-shrink:0}
.site-hd .hd-dd-menu a .hd-dd-ic svg{width:100%;height:100%}
.site-hd .hd-sep{color:rgba(255,255,255,.35);font-size:12px;user-select:none}
.site-hd .hd-ic{display:inline-flex;color:#fff;opacity:.9}
.site-hd .hd-ic:hover{opacity:1}
.site-hd .hd-ic svg{width:17px;height:17px}
@media(max-width:680px){.site-hd .hd-in{padding:11px 14px}.site-hd .hd-links{gap:12px}.site-hd a,.site-hd .hd-dd-btn{font-size:11.5px}.site-hd .hd-sep{display:none}.site-hd .hd-dd-menu{grid-template-columns:repeat(2,1fr);width:auto;max-width:calc(100vw - 28px)}}
</style><div class="hd-in"><a class="hd-home" href="/">Home</a><nav class="hd-links"><div class="hd-dd" id="hdDd"><button class="hd-dd-btn" id="hdDdBtn" type="button" aria-haspopup="true" aria-expanded="false" aria-controls="hdDdMenu">Tools<svg class="hd-chev" viewBox="0 0 12 12" fill="none"><path d="M2.5 4.5L6 8l3.5-3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></button><div class="hd-dd-menu" id="hdDdMenu" role="group" aria-label="Tools"><div class="hd-dd-cat">Earthquake Science</div><a href="/earthquake-rupture/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/></svg></span><span class="hd-dd-lbl">Fault Mechanism</span></a><a href="/world-faults/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.7 2.6 4 5.6 4 9s-1.3 6.4-4 9c-2.7-2.6-4-5.6-4-9s1.3-6.4 4-9z"/></svg></span><span class="hd-dd-lbl">Global Faults & Live Earthquakes</span></a><a href="/earthquake-dashboard/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l2.5-7 5 14 2.5-7h4"/></svg></span><span class="hd-dd-lbl">Rapid Response</span></a><a href="/world-faults/stats/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 20h18M6 20V10M12 20V4M18 20v-7"/></svg></span><span class="hd-dd-lbl">Earthquake Statistics</span></a><div class="hd-dd-cat">Catastrophe Risk</div><a href="/hazus/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 18h18M5 18V9l4-4 4 4v9M13 18v-6l3-3 3 3v6"/></svg></span><span class="hd-dd-lbl">Vulnerability Explorer</span></a><a href="/hazard-sequence-simulator/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M2 10h3l2-6 4 12 2-6 2 3h3"/><path d="M7 19l1-2.5M11 19.5l1-2.5M15 19l1-2.5"/></svg></span><span class="hd-dd-lbl">Hazard Sequence Simulator</span></a><a href="/slope-seismic-vulnerability/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 19h18"/><path d="M5 19L14 6l5 13"/><path d="M9.5 12.5l8.5 1"/></svg></span><span class="hd-dd-lbl">Slope Seismic Vulnerability</span></a><div class="hd-dd-cat">Structural Analysis</div><a href="/rc-section-designer/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9"><rect x="4.5" y="5" width="15" height="14" rx="1.5"/><circle cx="9" cy="9.5" r="1.1" fill="#fff" stroke="none"/><circle cx="15" cy="9.5" r="1.1" fill="#fff" stroke="none"/><circle cx="9" cy="14.5" r="1.1" fill="#fff" stroke="none"/><circle cx="15" cy="14.5" r="1.1" fill="#fff" stroke="none"/></svg></span><span class="hd-dd-lbl">RC Section Designer</span></a><a href="/modal-analysis/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 14c2-6 4-6 5 0s3 6 5 0 3-6 5 0 3 6 5 0"/></svg></span><span class="hd-dd-lbl">Modal Analysis</span></a><a href="/design-spectrum/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 17C4 14 5 9 6.5 7L13 7C14 9 14.5 10.5 15.5 12C17 14.5 18.5 16 21 18"/></svg></span><span class="hd-dd-lbl">Design Spectrum</span></a><a href="/performance-point-evaluator/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M5 5l14 14M19 5L5 19"/><circle cx="12" cy="12" r="1.7" fill="#fff" stroke="none"/></svg></span><span class="hd-dd-lbl">Performance Point Evaluator</span></a><a href="/ground-motion/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h3l2-7 4 14 3-10 2 6h4"/></svg></span><span class="hd-dd-lbl">Ground Motion Analyzer</span></a><a href="/building-response/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="3" width="14" height="18" rx="1.5"/><path d="M9 21v-4h6v4"/><path d="M8 7h.01M12 7h.01M16 7h.01M8 11h.01M12 11h.01M16 11h.01"/></svg></span><span class="hd-dd-lbl">Building Response Lab</span></a><a href="/material-behaviour-explorer/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19c3-.5 4.2-3.4 5.2-6.2C10.2 10 12 6 14.7 6c2 0 3 1.7 3 4 0 2.6-1 5-2.7 7"/><circle cx="9.3" cy="12.9" r="1.1" fill="#fff" stroke="none"/></svg></span><span class="hd-dd-lbl">Material Behaviour Explorer</span></a></div></div><span class="hd-sep">|</span><a href="/about/">About</a><span class="hd-sep">|</span><a href="/contact/">Contact</a><span class="hd-sep">|</span><a class="hd-ic" href="https://www.youtube.com/@Structural.Analysis" target="_blank" rel="noopener" aria-label="YouTube"><svg viewBox="0 0 24 24" fill="none"><rect x="2.5" y="5.5" width="19" height="13" rx="3.5" stroke="currentColor" stroke-width="1.8"/><path d="M10.3 9.4v5.2l4.6-2.6-4.6-2.6z" fill="currentColor"/></svg></a><a class="hd-ic" href="https://www.linkedin.com/in/arashnassirpour/" target="_blank" rel="noopener" aria-label="LinkedIn"><svg viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="18" rx="3" stroke="currentColor" stroke-width="1.8"/><path d="M8 10.5V17M8 7.2v.1M12 17v-3.7c0-1.3.9-2.3 2.2-2.3 1.3 0 2.3 1 2.3 2.3V17" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></a></nav></div>
<script>
(function(){
  var dd = document.getElementById('hdDd');
  var btn = document.getElementById('hdDdBtn');
  var menu = dd ? dd.querySelector('.hd-dd-menu') : null;
  if(!dd||!btn||!menu) return;
  function positionMenu(){
    var r = btn.getBoundingClientRect();
    menu.style.top = (r.bottom + 10) + 'px';
    var left = r.right - menu.offsetWidth;
    if (left < 10) left = 10;
    menu.style.left = left + 'px';
  }
  function setOpen(open){
    dd.classList.toggle('open', open);
    btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    if (open) positionMenu();
  }
  function isOpen(){ return dd.classList.contains('open'); }

  btn.addEventListener('click', function(e){
    e.stopPropagation();
    setOpen(!isOpen());
  });
  document.addEventListener('click', function(){ setOpen(false); });
  window.addEventListener('resize', function(){ if (isOpen()) positionMenu(); });
  window.addEventListener('scroll', function(){ if (isOpen()) positionMenu(); }, true);
  menu.addEventListener('click', function(e){ e.stopPropagation(); });

  /* keyboard: Escape closes and returns focus, Down opens and enters the menu */
  document.addEventListener('keydown', function(e){
    if (e.key === 'Escape' && isOpen()){
      setOpen(false);
      btn.focus();
    }
  });
  btn.addEventListener('keydown', function(e){
    if (e.key === 'ArrowDown'){
      e.preventDefault();
      if (!isOpen()) setOpen(true);
      var first = menu.querySelector('a');
      if (first) first.focus();
    }
  });
  /* tabbing out of the last item closes the menu */
  menu.addEventListener('focusout', function(e){
    if (!menu.contains(e.relatedTarget) && e.relatedTarget !== btn) setOpen(false);
  });
})();
</script>
</header>""",
        '<div class="ea-bar ea-show" id="ea-bar">'
        '  <div class="ea-label"><span class="ea-dot"></span>GLOBAL DISASTER ALERTS</div>'
        '  <div class="ea-track"><div class="ea-scroll" id="ea-scroll"><span class="ea-item" style="cursor:default;color:#b91c1c">Loading latest alerts&hellip;</span></div></div>'
        '  <div class="ea-controls">'
        '    <button class="ea-nav" id="ea-prev" type="button" title="Previous alert" aria-label="Previous alert" disabled>'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M15 6l-6 6 6 6"/></svg></button>'
        '    <button class="ea-play" id="ea-play" type="button" title="Pause" aria-label="Pause" disabled>'
        '<svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg></button>'
        '    <button class="ea-nav" id="ea-next" type="button" title="Next alert" aria-label="Next alert" disabled>'
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M9 6l6 6-6 6"/></svg></button>'
        '  </div>'
        '  <select class="ea-filter" id="ea-filter" aria-label="Filter disaster alerts">'
        '    <option value="all">All hazards</option>'
        '    <option value="serious">Serious alerts (Orange &amp; Red)</option>'
        '    <option value="Earthquake">Earthquakes</option>'
        '    <option value="storm">Cyclones &amp; storms</option>'
        '    <option value="Flood">Floods</option>'
        '    <option value="Volcano">Volcanoes</option>'
        '    <option value="Wildfire">Wildfires</option>'
        '    <option value="other">Other</option>'
        '  </select>'
        "</div>",
        "<script>" + ERCC_UPGRADE_JS + "</script>",
        '<div class="nav">',
        "  <div>",
        '    <h1 class="nav-title"><span class="live"></span>Earthquake Rapid Response Dashboard</h1>',
        "  </div>",
        '  <div style="font-size:11px;color:#64748b;text-align:right"><span style="font-weight:600;color:#1a1f36">Last update:</span> ' + html.escape(now_str) + "</div>",
        "</div>",
        '<div class="body" role="main">',
        '  <div class="sidebar">',
        '    <div class="sb-hdr"><div class="sb-title">Top Events - Last 90 Days</div></div>',
        '    <div class="sb-legend">',
        '      <span><span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#2e7d32;margin-right:3px;vertical-align:middle"></span>ShakeMap</span>',
        '      <span><span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#ccc;margin-right:3px;vertical-align:middle"></span>Pending</span>',
        "    </div>",
        '    <div class="sb-list">' + sb + "</div>",
        "  </div>",
        '  <div class="rp"><div id="rp-inner"></div>' + '<section class="platform-guide" aria-labelledby="platform-guide-title"><h2 id="platform-guide-title">Using earthquake rapid response</h2><p>Read a source-linked briefing for significant earthquakes, including USGS ShakeMap, PAGER, ground-failure and aftershock products when available. Product status and update times matter.</p><details><summary>Try a worked example</summary><ol><li>Choose an earthquake from Top Events.</li><li>Compare PGA and MMI map layers: ground acceleration and felt intensity describe different quantities.</li><li>Open the original USGS event and product links to inspect their timestamps, status and assumptions.</li></ol></details><nav aria-label="Related tools"><a href="/world-faults/">World fault map</a><a href="/earthquake-rupture/">Fault mechanism</a></nav></section>' + '</div>',
        "</div>",
        # Shared site footer - keep identical across all arashnassirpour.com repos.
        # Placed here, as the last item inside .app-shell (flex-shrink:0), so it
        # sits at the bottom of the fixed-height app view instead of under the header.
        """<footer class="site-ft"><style>
.site-ft{background:#0f2350;border-top:1px solid rgba(255,255,255,.08);flex-shrink:0;line-height:normal;font-family:Inter,'Segoe UI',system-ui,sans-serif}
.site-ft .ft-in{max-width:1080px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;padding:14px 24px}
.site-ft .ft-copy{font-size:12.5px;color:#fff}
.site-ft .ft-links{display:flex;align-items:center;gap:16px}
.site-ft .ft-links a{text-decoration:none;color:#fff;font-size:12.5px;font-weight:500;transition:color .15s;opacity:.85}
.site-ft .ft-links a:hover{opacity:1}
.site-ft .ft-ic{display:inline-flex;color:#fff;opacity:.85}
.site-ft .ft-ic:hover{opacity:1}
.site-ft .ft-ic svg{width:17px;height:17px}
@media(max-width:520px){.site-ft .ft-in{justify-content:center;text-align:center}}
</style><div class="ft-in"><span class="ft-copy">&copy; 2026 Arash Nassirpour. All rights reserved.</span><nav class="ft-links"><a href="/about/">About</a><a href="/contact/">Contact</a><a class="ft-ic" href="https://www.youtube.com/@Structural.Analysis" target="_blank" rel="noopener" aria-label="YouTube"><svg viewBox="0 0 24 24" fill="none"><rect x="2.5" y="5.5" width="19" height="13" rx="3.5" stroke="currentColor" stroke-width="1.8"/><path d="M10.3 9.4v5.2l4.6-2.6-4.6-2.6z" fill="currentColor"/></svg></a><a class="ft-ic" href="https://www.linkedin.com/in/arashnassirpour/" target="_blank" rel="noopener" aria-label="LinkedIn"><svg viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="18" rx="3" stroke="currentColor" stroke-width="1.8"/><path d="M8 10.5V17M8 7.2v.1M12 17v-3.7c0-1.3.9-2.3 2.2-2.3 1.3 0 2.3 1 2.3 2.3V17" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></a></nav></div></footer>""",
        "</div>",
        '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>',
        "<script>" + js + "</script>",
        "</body></html>",
    ])
