# dashboard.py - Builds the HTML dashboard from event data.
# The client-side JS lives in dashboard_js.js (single source of truth) and is
# read at build time; data is injected via __PLACEHOLDER__ tokens.

import html
import json
from pathlib import Path

from settings import ALERT_C, MMI_C, PAGER_D, JS_FILE

HERE = Path(__file__).resolve().parent

# ── Sidebar (server-rendered) ─────────────────────────────────────────────────

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
body{font-family:'Segoe UI',system-ui,sans-serif;background:#f0f2f8;display:flex;flex-direction:column;height:100vh;overflow:hidden;font-size:13px;color:#1a1f36}
.nav{display:flex;justify-content:space-between;align-items:center;background:#fff;border-bottom:1px solid #e2e6f0;padding:11px 20px;flex-shrink:0;box-shadow:0 1px 6px rgba(0,0,0,.06)}
.nav-title{font-size:15px;font-weight:700}.nav-sub{font-size:11px;color:#64748b}
.live{width:8px;height:8px;border-radius:50%;background:#2e7d32;display:inline-block;margin-right:7px;animation:pulse 2s infinite;vertical-align:middle}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}
.body{display:flex;flex:1;overflow:hidden}
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
        "<title>Latest Earthquakes - Live Dashboard with ShakeMaps and Aftershock Forecasts</title>",
        '<meta name="description" content="The largest earthquakes of the past 30 days: ShakeMap ground motion, aftershock probabilities, fault mechanisms and impact intelligence. Automatically updated every 6 hours from USGS data." />',
        '<link rel="canonical" href="https://arashnassirpour.com/earthquake-dashboard/" />',
        '<meta property="og:title" content="Latest Earthquakes - Live Dashboard" />',
        '<meta property="og:description" content="ShakeMaps, aftershock forecasts and impact intelligence for the largest recent earthquakes. Updates every 6 hours." />',
        '<meta property="og:url" content="https://arashnassirpour.com/earthquake-dashboard/" />',
        '<meta property="og:type" content="website" />',
        "<!-- Google Analytics -->",
        '<script async src="https://www.googletagmanager.com/gtag/js?id=G-0WERZ6WKQY"></script>',
        "<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}"
        'gtag("js",new Date());gtag("config","G-0WERZ6WKQY");</script>',
        '<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>',
        "<style>" + CSS + "</style>",
        "</head><body>",
        # Shared site navigation - IDENTICAL markup on all arashnassirpour.com pages.
        # If you change it here, change it in personal-site, earthquake-rupture
        # and world-faults too.
        """<!-- shared site navigation -->
<nav class="sw-bar"><style>
.sw-bar{position:relative;z-index:2000;background:#101522;font-family:Inter,'Segoe UI',system-ui,sans-serif;display:flex;justify-content:space-between;align-items:center;padding:9px 18px;font-size:13px;flex-shrink:0;line-height:1}
.sw-bar a{color:#aab3c5;text-decoration:none;font-weight:600;margin-left:16px;transition:color .15s}
.sw-bar a:hover{color:#fff}
.sw-bar a.sw-home{margin-left:0;font-weight:800;color:#fff}
.sw-bar a.sw-on{color:#fff;border-bottom:2px solid #2458ff;padding-bottom:2px}
@media(max-width:560px){.sw-bar{font-size:12px;padding:8px 12px}.sw-bar a{margin-left:10px}}
</style><a class="sw-home" href="/">Home</a><div><a href="/earthquake-rupture/">Fault mechanism</a><a href="/world-faults/">Global faults</a><a class="sw-on" href="/earthquake-dashboard/">Latest earthquakes</a><a href="/rc-section-designer/">Section designer</a></div></nav>""",
        '<div class="nav">',
        "  <div>",
        '    <div class="nav-title"><span class="live"></span>Earthquake Rapid Response Dashboard</div>',
        '    <div class="nav-sub">Live earthquake briefing - updates every 6 hours</div>',
        "  </div>",
        '  <div style="font-size:11px;color:#64748b;text-align:right">' + html.escape(now_str)
        + "<br>USGS NEIC / PAGER / ShakeMap</div>",
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
        '<div style="flex-shrink:0;background:#fff;border-top:1px solid #e2e6f0;padding:7px 20px;font-size:11px;color:#64748b;text-align:center">'
        '&copy; 2026 <a href="/" style="color:inherit">Arash Nassirpour</a> &middot; <a href="/" style="color:inherit">Home</a> &middot; <a href="https://www.youtube.com/@Structural.Analysis" target="_blank" rel="noopener" style="color:inherit">YouTube</a> &middot; <a href="https://www.linkedin.com/in/arashnassirpour/" target="_blank" rel="noopener" style="color:inherit">LinkedIn</a> &middot; Preliminary information, not for emergency response.</div>',
        '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>',
        "<script>" + js + "</script>",
        "</body></html>",
    ])
