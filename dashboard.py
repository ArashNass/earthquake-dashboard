# dashboard.py - Builds the HTML dashboard from event data.
# The client-side JS lives in dashboard_js.js (single source of truth) and is
# read at build time; data is injected via __PLACEHOLDER__ tokens.

import html
import json
from pathlib import Path

from settings import ALERT_C, MMI_C, PAGER_D, JS_FILE

HERE = Path(__file__).resolve().parent

ERCC_UPGRADE_JS = """
(function(){
  var eonetUrl = 'https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=12';
  var usgsUrl  = 'https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.geojson';
  console.log('[disaster-alerts] fetching', eonetUrl, 'and', usgsUrl);

  function esc(s){ return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }

  var eonetItems = fetch(eonetUrl).then(function(r){
    console.log('[disaster-alerts] EONET response status', r.status);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }).then(function(data){
    var events = (data && data.events) || [];
    return events.map(function(ev){
      var cat = (ev.categories && ev.categories[0] && ev.categories[0].title) || '';
      var title = cat ? (cat + ': ' + ev.title) : ev.title;
      return { title: (title || '').trim(), link: ev.link || (ev.sources && ev.sources[0] && ev.sources[0].url) || '', source: 'eonet' };
    }).filter(function(it){ return it.title && it.link; });
  }).catch(function(e){ console.log('[disaster-alerts] EONET failed:', e.message || e); return []; });

  var usgsItems = fetch(usgsUrl).then(function(r){
    console.log('[disaster-alerts] USGS response status', r.status);
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  }).then(function(data){
    var feats = (data && data.features) || [];
    return feats.map(function(f){
      var p = f.properties || {};
      return { title: 'Earthquake: ' + (p.title || p.place || ''), link: p.url || '', source: 'usgs' };
    }).filter(function(it){ return it.title && it.link; });
  }).catch(function(e){ console.log('[disaster-alerts] USGS failed:', e.message || e); return []; });

  Promise.all([eonetItems, usgsItems]).then(function(results){
    var allItems = results[0].concat(results[1]);
    console.log('[disaster-alerts] combined items:', allItems.length, '(EONET:', results[0].length, ', USGS:', results[1].length, ')');

    var scroll = document.getElementById('ea-scroll');
    var bar = document.getElementById('ea-bar');
    var filterEl = document.getElementById('ea-filter');
    if (!scroll || !bar) { console.log('[disaster-alerts] DOM elements not found'); return; }

    if (!allItems.length) {
      console.log('[disaster-alerts] no items from either source');
      scroll.innerHTML = '<span class="ea-item" style="cursor:default;color:#8fa8c4">No live alerts available right now</span>';
      if (filterEl) filterEl.style.display = 'none';
      return;
    }

    function render(filter){
      var items = filter === 'all' ? allItems : allItems.filter(function(it){ return it.source === filter; });
      if (!items.length){ scroll.innerHTML = '<span class="ea-item" style="cursor:default">No events for this filter</span>'; return; }
      var chips = items.map(function(it){
        return '<a class="ea-item" href="' + esc(it.link) + '" target="_blank" rel="noopener">' + esc(it.title) + '</a><span class="ea-sep">&#8226;</span>';
      }).join('');
      scroll.innerHTML = chips + chips;
      // Duration scales with content so reading speed stays roughly constant regardless of item count.
      scroll.style.animationDuration = Math.max(40, items.length * 9) + 's';
    }

    render('all');
    if (filterEl) filterEl.addEventListener('change', function(){ render(this.value); });
    console.log('[disaster-alerts] banner shown with', allItems.length, 'items');
  });
})();
"""



def sidebar_item(e, selected):
    ac  = ALERT_C.get(e.get("alert") or "", ALERT_C[""])
    sel = "background:#e8f0fe;border-left:3px solid #1565c0;" if selected else "border-left:3px solid transparent;"
    dot = "#2e7d32" if e.get("has_shakemap") else "#ccc"
    place = e.get("place") or "Unknown location"
    pl  = html.escape(place[:44] + ("..." if len(place) > 44 else ""))
    mag = round(float(e.get("mag") or 0), 1)
    alert = html.escape(e.get("alert") or "N/A")
    # Click handling is done via event delegation in JS; only data-id is needed.
    return (
        '<div class="ev-item" data-id="' + html.escape(e["id"], quote=True) + '" '
        'style="' + sel + 'cursor:pointer;padding:10px 14px;border-bottom:1px solid #eee;">'
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:2px">'
        '<span style="font-size:18px;font-weight:900;color:' + ac + '">M' + str(mag) + '</span>'
        '<span style="display:flex;align-items:center;gap:5px">'
        '<span style="font-size:9px;font-weight:700;color:' + ac + ';text-transform:uppercase">' + alert + '</span>'
        '<span style="width:7px;height:7px;border-radius:50%;background:' + dot + ';display:inline-block"></span>'
        '</span></div>'
        '<div style="font-size:11px;font-weight:600;color:#1a1f36;margin-bottom:2px">' + pl + '</div>'
        '<div style="font-size:10px;color:#888">' + html.escape(e.get("age_str", "")) + ' - '
        + str(round(float(e.get("depth") or 0))) + ' km</div>'
        '</div>'
    )

# ── Serialise event data for JSON embedding ───────────────────────────────────

_EV_KEYS_DEFAULTS = {
    "event_id": "", "mag": 0, "place": "", "lat": 0, "lon": 0, "depth": 0,
    "depth_note": "", "t_str": "", "t_age_str": "", "alert_color": ALERT_C[""],
    "alert_lbl": "N/A", "pager_alert": "N/A", "pager_color": ALERT_C[""],
    "mmi": 0, "mmi_label": "--", "mmi_desc": "--", "mmi_effect": "",
    "mmi_color": "#ccc", "tectonic": "", "energy_mt": 0, "rupture_km": 0,
    "tsunami": False, "url": "",
}


def serialize(data):
    ev = data.get("ev") or {}
    sm = data.get("sm") or {}
    return {
        "ev":         {k: ev.get(k, dflt) for k, dflt in _EV_KEYS_DEFAULTS.items()},
        "sm":         {"mmi_url": sm.get("mmi_url", ""), "pga_url": sm.get("pga_url", "")},
        "aftershock": data.get("aftershock"),
        "focal":      data.get("focal"),
        "historical": data.get("historical") or [],
        "weather":    data.get("weather"),
        "building":   data.get("building"),
        "news":       data.get("news") or [],
        "narrative":  data.get("narrative"),
    }


def _json_for_script(obj):
    """JSON that is safe to embed inside a <script> element."""
    return (json.dumps(obj, ensure_ascii=False)
            .replace("<", "\\u003c")
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))

# ── CSS ───────────────────────────────────────────────────────────────────────

CSS = """\
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',system-ui,sans-serif;background:#f0f2f8;display:flex;flex-direction:column;min-height:100vh;font-size:13px;color:#1a1f36}
.nav{display:flex;justify-content:space-between;align-items:center;background:#fff;border-bottom:1px solid #e2e6f0;padding:11px 20px;flex-shrink:0;box-shadow:0 1px 6px rgba(0,0,0,.06)}
.nav-title{font-size:15px;font-weight:700}.nav-sub{font-size:11px;color:#64748b}
.ea-bar{display:none;align-items:center;gap:16px;background:#3a1f10;padding:12px 22px;flex-shrink:0;overflow:hidden;box-shadow:0 2px 10px rgba(0,0,0,.15)}
.ea-bar.ea-show{display:flex}
.ea-label{display:flex;align-items:center;gap:7px;font-size:12px;font-weight:800;letter-spacing:.8px;color:#fff;white-space:nowrap;flex-shrink:0;background:#c0281f;padding:5px 12px;border-radius:4px}
.ea-dot{width:7px;height:7px;border-radius:50%;background:#fff;flex-shrink:0;animation:pulse 2s infinite}
.ea-track{flex:1;overflow:hidden;white-space:nowrap;mask-image:linear-gradient(90deg,transparent,#000 24px,#000 calc(100% - 24px),transparent);-webkit-mask-image:linear-gradient(90deg,transparent,#000 24px,#000 calc(100% - 24px),transparent)}
.ea-scroll{display:inline-block;animation:ea-marquee 140s linear infinite}
.ea-track:hover .ea-scroll{animation-play-state:paused}
.ea-item{color:#fce9d8;text-decoration:none;font-size:14px;font-weight:600;padding:0 4px}
.ea-item:hover{color:#fff;text-decoration:underline}
.ea-sep{color:#a37a5c;margin:0 26px;font-size:12px}
.ea-more{flex-shrink:0;color:#e8b98a;font-size:10.5px;font-weight:600;text-decoration:none;white-space:nowrap}
.ea-more:hover{color:#fff}
.ea-filter{flex-shrink:0;background:#5a3620;color:#fce9d8;border:1px solid #7a4a30;border-radius:5px;font-size:11px;font-weight:700;padding:5px 9px;cursor:pointer}
.ea-filter:hover{border-color:#e8b98a}
.ea-filter option{background:#3a1f10;color:#fff}
@keyframes ea-marquee{from{transform:translateX(0)}to{transform:translateX(-50%)}}
@media(max-width:680px){.ea-filter{font-size:9px;padding:3px 6px}.ea-item{font-size:12px}.ea-label{font-size:10px;padding:4px 8px}}
.live{width:8px;height:8px;border-radius:50%;background:#2e7d32;display:inline-block;margin-right:7px;animation:pulse 2s infinite;vertical-align:middle}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.body{display:flex;flex:none;height:calc(100vh - 152px);min-height:420px;overflow:hidden}
.sidebar{width:272px;flex-shrink:0;background:#fff;border-right:1px solid #e2e6f0;display:flex;flex-direction:column;overflow:hidden}
.sb-hdr{padding:10px 14px;border-bottom:1px solid #e2e6f0;background:#f8f9fc;flex-shrink:0}
.sb-title{font-size:10px;font-weight:700;color:#64748b;text-transform:uppercase;letter-spacing:1px}
.sb-legend{display:flex;gap:14px;font-size:10px;color:#888;padding:6px 14px;border-bottom:1px solid #e2e6f0;flex-shrink:0}
.sb-list{overflow-y:auto;flex:1}.ev-item:hover{background:#f0f4ff!important}
.rp{flex:1;overflow-y:auto;background:#f0f2f8}
#rp-inner{padding:16px;max-width:1060px;margin:0 auto}
@media(max-width:760px){
  body{overflow:auto;height:auto}
  .body{flex-direction:column;overflow:visible}
  .sidebar{width:100%;border-right:none;border-bottom:1px solid #e2e6f0}
  .sb-list{display:flex;overflow-x:auto;overflow-y:hidden}
  .ev-item{min-width:200px;border-right:1px solid #eee}
  .rp{overflow:visible}
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
          .replace("__ALERT_C__",    _json_for_script(ALERT_C))
          .replace("__PAGER_DESC__", _json_for_script(PAGER_D)))

    return "\n".join([
        "<!DOCTYPE html>",
        '<html lang="en"><head>',
        '<meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        "<title>Rapid Earthquake Response - Live Dashboard with ShakeMaps and Aftershock Forecasts</title>",
        '<meta name="description" content="Rapid Earthquake Response: the largest earthquakes of the past 30 days with ShakeMap ground motion, aftershock probabilities, fault mechanisms and impact intelligence, plus live global disaster alerts." />',
        '<link rel="canonical" href="https://arashnassirpour.com/earthquake-dashboard/" />',
        '<meta property="og:title" content="Rapid Earthquake Response - Live Dashboard" />',
        '<meta property="og:description" content="ShakeMaps, aftershock forecasts and impact intelligence for the largest recent earthquakes, with live global disaster alerts." />',
        '<meta property="og:url" content="https://arashnassirpour.com/earthquake-dashboard/" />',
        '<meta property="og:type" content="website" />',
        '<script type="application/ld+json">'
        '{"@context":"https://schema.org","@type":"SoftwareApplication","name":"Rapid Earthquake Response",'
        '"applicationCategory":"EngineeringApplication","operatingSystem":"Web",'
        '"url":"https://arashnassirpour.com/earthquake-dashboard/",'
        '"description":"Live USGS earthquake briefing with ShakeMaps, aftershock forecasts, and a global disaster alerts ticker.",'
        '"offers":{"@type":"Offer","price":"0","priceCurrency":"USD"},'
        '"author":{"@type":"Person","name":"Arash Nassirpour"}}'
        '</script>',
        "<!-- Google Analytics -->",
        '<script async src="https://www.googletagmanager.com/gtag/js?id=G-0WERZ6WKQY"></script>',
        "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
        'gtag("js",new Date());gtag("config","G-0WERZ6WKQY");</script>',
        '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>',
        "<style>" + CSS + "</style>",
        "</head><body>",
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
.site-hd .hd-dd-menu{position:fixed;background:#1f3d78;border:1px solid rgba(255,255,255,.12);border-radius:12px;box-shadow:0 16px 40px rgba(0,0,0,.4);padding:8px;display:none;gap:2px;z-index:10000}
.site-hd .hd-dd.open .hd-dd-menu{display:flex}
.site-hd .hd-dd-menu a{display:flex;flex-direction:column;align-items:center;gap:7px;width:96px;padding:12px 8px;border-radius:8px;font-size:11px;color:#fff;font-weight:500;text-align:center;line-height:1.3;opacity:.92}
.site-hd .hd-dd-menu a:hover{background:rgba(255,255,255,.1);opacity:1}
.site-hd .hd-dd-menu a.hd-on{background:rgba(255,255,255,.16);opacity:1}
.site-hd .hd-dd-menu a .hd-dd-ic{width:22px;height:22px}
.site-hd .hd-dd-menu a .hd-dd-ic svg{width:100%;height:100%}
.site-hd .hd-sep{color:rgba(255,255,255,.35);font-size:12px;user-select:none}
.site-hd .hd-ic{display:inline-flex;color:#fff;opacity:.9}
.site-hd .hd-ic:hover{opacity:1}
.site-hd .hd-ic svg{width:17px;height:17px}
@media(max-width:680px){.site-hd .hd-in{padding:11px 14px}.site-hd .hd-links{gap:12px}.site-hd a,.site-hd .hd-dd-btn{font-size:11.5px}.site-hd .hd-sep{display:none}.site-hd .hd-dd-menu{padding:6px;flex-wrap:wrap;max-width:calc(100vw - 28px)}.site-hd .hd-dd-menu a{width:84px}}
</style><div class="hd-in"><a class="hd-home" href="/">Home</a><nav class="hd-links"><div class="hd-dd" id="hdDd"><button class="hd-dd-btn" id="hdDdBtn" type="button">Tools<svg class="hd-chev" viewBox="0 0 12 12" fill="none"><path d="M2.5 4.5L6 8l3.5-3.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></button><div class="hd-dd-menu"><a href="/earthquake-rupture/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#534AB7" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3z"/><path d="M12 12l8-4.5M12 12v9M12 12L4 7.5"/></svg></span>Fault Mechanism</a><a href="/world-faults/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#0F6E56" stroke-width="1.9" stroke-linecap="round"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.7 2.6 4 5.6 4 9s-1.3 6.4-4 9c-2.7-2.6-4-5.6-4-9s1.3-6.4 4-9z"/></svg></span>Global Faults & Live Earthquakes</a><a href="/earthquake-dashboard/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#A32D2D" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h4l2.5-7 5 14 2.5-7h4"/></svg></span>Rapid Earthquake Response</a><a href="/rc-section-designer/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#854F0B" stroke-width="1.9"><rect x="4.5" y="5" width="15" height="14" rx="1.5"/><circle cx="9" cy="9.5" r="1.1" fill="#854F0B" stroke="none"/><circle cx="15" cy="9.5" r="1.1" fill="#854F0B" stroke="none"/><circle cx="9" cy="14.5" r="1.1" fill="#854F0B" stroke="none"/><circle cx="15" cy="14.5" r="1.1" fill="#854F0B" stroke="none"/></svg></span>Reinforced Concrete Section Designer</a><a href="/hazus/"><span class="hd-dd-ic"><svg viewBox="0 0 24 24" fill="none" stroke="#1E6B8C" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 18h18M5 18V9l4-4 4 4v9M13 18v-6l3-3 3 3v6"/></svg></span>Vulnerability Explorer</a></div></div><span class="hd-sep">|</span><a href="/contact/">Contact</a><span class="hd-sep">|</span><a class="hd-ic" href="https://www.youtube.com/@Structural.Analysis" target="_blank" rel="noopener" aria-label="YouTube"><svg viewBox="0 0 24 24" fill="none"><rect x="2.5" y="5.5" width="19" height="13" rx="3.5" stroke="currentColor" stroke-width="1.8"/><path d="M10.3 9.4v5.2l4.6-2.6-4.6-2.6z" fill="currentColor"/></svg></a><a class="hd-ic" href="https://www.linkedin.com/in/arashnassirpour/" target="_blank" rel="noopener" aria-label="LinkedIn"><svg viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="18" rx="3" stroke="currentColor" stroke-width="1.8"/><path d="M8 10.5V17M8 7.2v.1M12 17v-3.7c0-1.3.9-2.3 2.2-2.3 1.3 0 2.3 1 2.3 2.3V17" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></a></nav></div>
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
  btn.addEventListener('click', function(e){
    e.stopPropagation();
    dd.classList.toggle('open');
    if (dd.classList.contains('open')) positionMenu();
  });
  document.addEventListener('click', function(){ dd.classList.remove('open'); });
  window.addEventListener('resize', function(){ if (dd.classList.contains('open')) positionMenu(); });
  window.addEventListener('scroll', function(){ if (dd.classList.contains('open')) positionMenu(); }, true);
  menu.addEventListener('click', function(e){ e.stopPropagation(); });
})();
</script>
</header>""",
        '<div class="ea-bar ea-show" id="ea-bar">'
        '  <div class="ea-label"><span class="ea-dot"></span>GLOBAL DISASTER ALERTS</div>'
        '  <div class="ea-track"><div class="ea-scroll" id="ea-scroll"><span class="ea-item" style="cursor:default;color:#8fa8c4">Loading latest alerts&hellip;</span></div></div>'
        '  <select class="ea-filter" id="ea-filter">'
        '    <option value="all">All Sources</option>'
        '    <option value="eonet">Wildfires, Storms &amp; More</option>'
        '    <option value="usgs">Earthquakes Only</option>'
        '  </select>'
        "</div>",
        "<script>" + ERCC_UPGRADE_JS + "</script>",
        '<div class="nav">',
        "  <div>",
        '    <div class="nav-title"><span class="live"></span>Earthquake Rapid Response Dashboard</div>',
        "  </div>",
        '  <div style="font-size:11px;color:#64748b;text-align:right">' + html.escape(now_str) + "</div>",
        "</div>",
        '<div class="body">',
        '  <div class="sidebar">',
        '    <div class="sb-hdr"><div class="sb-title">Top Events - Last 30 Days</div></div>',
        '    <div class="sb-legend">',
        '      <span><span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#2e7d32;margin-right:3px;vertical-align:middle"></span>ShakeMap</span>',
        '      <span><span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#ccc;margin-right:3px;vertical-align:middle"></span>Pending</span>',
        "    </div>",
        '    <div class="sb-list">' + sb + "</div>",
        "  </div>",
        '  <div class="rp"><div id="rp-inner"></div></div>',
        "</div>",
        """<footer class="site-ft"><style>
.site-ft{background:#0f2350;border-top:1px solid rgba(255,255,255,.08);flex-shrink:0;font-family:Inter,'Segoe UI',system-ui,sans-serif}
.site-ft .ft-in{max-width:1080px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;padding:14px 24px}
.site-ft .ft-copy{font-size:11.5px;color:#fff}
.site-ft .ft-links{display:flex;align-items:center;gap:16px}
.site-ft .ft-links a{text-decoration:none;color:#fff;font-size:11.5px;font-weight:500;transition:color .15s;opacity:.85}
.site-ft .ft-links a:hover{opacity:1}
.site-ft .ft-ic{display:inline-flex;color:#fff;opacity:.85}
.site-ft .ft-ic:hover{opacity:1}
.site-ft .ft-ic svg{width:15px;height:15px}
@media(max-width:520px){.site-ft .ft-in{justify-content:center;text-align:center}}
</style><div class="ft-in"><span class="ft-copy">&copy; 2026 Arash Nassirpour. All rights reserved.</span><nav class="ft-links"><a href="/contact/">Contact</a><a class="ft-ic" href="https://www.youtube.com/@Structural.Analysis" target="_blank" rel="noopener" aria-label="YouTube"><svg viewBox="0 0 24 24" fill="none"><rect x="2.5" y="5.5" width="19" height="13" rx="3.5" stroke="currentColor" stroke-width="1.8"/><path d="M10.3 9.4v5.2l4.6-2.6-4.6-2.6z" fill="currentColor"/></svg></a><a class="ft-ic" href="https://www.linkedin.com/in/arashnassirpour/" target="_blank" rel="noopener" aria-label="LinkedIn"><svg viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="18" rx="3" stroke="currentColor" stroke-width="1.8"/><path d="M8 10.5V17M8 7.2v.1M12 17v-3.7c0-1.3.9-2.3 2.2-2.3 1.3 0 2.3 1 2.3 2.3V17" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></a></nav></div></footer>""",
        '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>',
        "<script>" + js + "</script>",
        "</body></html>",
    ])
