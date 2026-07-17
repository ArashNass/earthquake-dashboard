# dashboard.py - Builds the HTML dashboard from event data.
# The client-side JS lives in dashboard_js.js (single source of truth) and is
# read at build time; data is injected via __PLACEHOLDER__ tokens.

import html
import json
import re
import urllib.request
import urllib.parse
from pathlib import Path

from settings import ALERT_C, MMI_C, PAGER_D, JS_FILE

HERE = Path(__file__).resolve().parent

RELIEFWEB_URL = "https://api.reliefweb.int/v2/reports"


def fetch_reliefweb_alerts(limit=8):
    """Fetch recent humanitarian/disaster report headlines from ReliefWeb
    (UN OCHA) - covers all disaster types worldwide, not just earthquakes.
    Public API, no auth required. Returns [] on any failure."""
    try:
        params = {
            "appname": "arashnassirpour-dashboard",
            "limit": str(limit),
            "sort[]": "date:desc",
            "fields[include][]": "title",
            "preset": "latest",
        }
        # url_alias is a separate include; urllib needs repeated keys handled manually
        query = urllib.parse.urlencode(params, doseq=True) + \
            "&fields[include][]=url_alias&fields[include][]=title"
        req = urllib.request.Request(
            RELIEFWEB_URL + "?" + query,
            headers={"User-Agent": "Mozilla/5.0 (compatible; arashnassirpour-dashboard/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
        items = []
        for entry in data.get("data", [])[:limit]:
            f = entry.get("fields", {})
            title = re.sub(r"\s+", " ", html.unescape((f.get("title") or "").strip()))
            link = f.get("url_alias") or entry.get("href") or ""
            if title and link:
                items.append({"title": title, "link": link})
        print(f"[reliefweb] fetched {len(items)} alert(s)")
        return items
    except Exception as e:
        print(f"[reliefweb] fetch failed: {type(e).__name__}: {e}")
        return []


def ercc_banner_html():
    """Live banner of recent global disaster/humanitarian headlines from
    ReliefWeb (UN OCHA). Falls back to a static EU Civil Protection (ERCC)
    portal link if the live fetch fails, so the banner never breaks."""
    alerts = fetch_reliefweb_alerts()
    if alerts:
        chips = "".join(
            '<a class="ea-item" href="{link}" target="_blank" rel="noopener">{title}</a>'
            '<span class="ea-sep">&#8226;</span>'.format(
                link=html.escape(a["link"]), title=html.escape(a["title"])
            )
            for a in alerts
        )
        return (
            '<div class="ea-bar">'
            '  <div class="ea-label"><span class="ea-dot"></span>GLOBAL DISASTER ALERTS</div>'
            '  <div class="ea-track"><div class="ea-scroll">' + chips + chips + "</div></div>"
            '  <a class="ea-more" href="https://reliefweb.int/updates" target="_blank" rel="noopener">ReliefWeb &rarr;</a>'
            "</div>"
        )
    return (
        '<div class="ea-bar">'
        '  <div class="ea-label"><span class="ea-dot"></span>EU CIVIL PROTECTION</div>'
        '  <div class="ea-text">Daily maps and flash reports on unfolding disasters and humanitarian crises worldwide, from the European Emergency Response Coordination Centre.</div>'
        '  <a class="ea-more" href="https://erccportal.jrc.ec.europa.eu/ECHO-Products/Maps" target="_blank" rel="noopener">Open ERCC Portal &rarr;</a>'
        "</div>"
    )



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
        '<a class="ercc-link" href="https://erccportal.jrc.ec.europa.eu/ECHO-Products/Maps" '
        'target="_blank" rel="noopener" onclick="event.stopPropagation()">EU Civil Protection &rarr;</a>'
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
.ea-bar{display:flex;align-items:center;gap:14px;background:#0F2A4A;padding:8px 20px;flex-shrink:0;overflow:hidden}
.ea-label{display:flex;align-items:center;gap:6px;font-size:10.5px;font-weight:700;letter-spacing:.6px;color:#fff;white-space:nowrap;flex-shrink:0}
.ea-dot{width:6px;height:6px;border-radius:50%;background:#ff5a5f;flex-shrink:0;animation:pulse 2s infinite}
.ea-text{flex:1;color:#cfe0f0;font-size:11.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ea-track{flex:1;overflow:hidden;white-space:nowrap;mask-image:linear-gradient(90deg,transparent,#000 24px,#000 calc(100% - 24px),transparent);-webkit-mask-image:linear-gradient(90deg,transparent,#000 24px,#000 calc(100% - 24px),transparent)}
.ea-scroll{display:inline-block;animation:ea-marquee 42s linear infinite}
.ea-track:hover .ea-scroll{animation-play-state:paused}
.ea-item{color:#cfe0f0;text-decoration:none;font-size:11.5px;font-weight:500}
.ea-item:hover{color:#fff;text-decoration:underline}
.ea-sep{color:#4c6b8c;margin:0 14px;font-size:10px}
.ea-more{flex-shrink:0;color:#8fc1e8;font-size:10.5px;font-weight:600;text-decoration:none;white-space:nowrap}
.ea-more:hover{color:#fff}
@keyframes ea-marquee{from{transform:translateX(0)}to{transform:translateX(-50%)}}
@media(max-width:680px){.ea-text{display:none}.ea-more{display:none}}
.ercc-link{display:inline-flex;align-items:center;gap:3px;font-size:9px;font-weight:600;color:#0F2A4A;text-decoration:none;margin-top:4px}
.ercc-link:hover{text-decoration:underline}
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
    ticker = ercc_banner_html()

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
        # Shared site header - keep identical across all arashnassirpour.com repos.
        """<!-- shared site header -->
<header class="site-hd"><style>
.site-hd{background:#fff;border-bottom:1px solid #e5e7eb;font-family:Inter,'Segoe UI',system-ui,sans-serif;flex-shrink:0}
.site-hd .hd-in{max-width:1080px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;padding:13px 24px}
.site-hd a{text-decoration:none;color:#5f6673;font-size:12.5px;font-weight:500;transition:color .15s}
.site-hd a:hover{color:#111827}
.site-hd .hd-home{color:#111827;font-size:13.5px;font-weight:600}
.site-hd .hd-links{display:flex;align-items:center;gap:24px}
.site-hd .hd-on{color:#111827;border-bottom:1.5px solid #2458ff;padding-bottom:2px}
.site-hd .hd-sep{color:#d1d5db;font-size:12px;user-select:none}
.site-hd .hd-ic{display:inline-flex;color:#5f6673}
.site-hd .hd-ic:hover{color:#111827}
.site-hd .hd-ic svg{width:17px;height:17px}
@media(max-width:680px){.site-hd .hd-in{padding:11px 14px}.site-hd .hd-links{gap:13px}.site-hd a{font-size:11.5px}.site-hd .hd-sep{display:none}}
</style><div class="hd-in"><a class="hd-home" href="/">Home</a><nav class="hd-links"><a href="/earthquake-rupture/">Fault Mechanism</a><span class="hd-sep">|</span><a href="/world-faults/">Global Faults</a><span class="hd-sep">|</span><a class="hd-on" href="/earthquake-dashboard/">Rapid Earthquake Response</a><span class="hd-sep">|</span><a href="/rc-section-designer/">Reinforced Concrete Section Designer</a><span class="hd-sep">|</span><a href="/hazus/">Vulnerability Explorer</a><span class="hd-sep">|</span><a class="hd-ic" href="https://www.youtube.com/@Structural.Analysis" target="_blank" rel="noopener" aria-label="YouTube"><svg viewBox="0 0 24 24" fill="none"><rect x="2.5" y="5.5" width="19" height="13" rx="3.5" stroke="currentColor" stroke-width="1.8"/><path d="M10.3 9.4v5.2l4.6-2.6-4.6-2.6z" fill="currentColor"/></svg></a><a class="hd-ic" href="https://www.linkedin.com/in/arashnassirpour/" target="_blank" rel="noopener" aria-label="LinkedIn"><svg viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="18" rx="3" stroke="currentColor" stroke-width="1.8"/><path d="M8 10.5V17M8 7.2v.1M12 17v-3.7c0-1.3.9-2.3 2.2-2.3 1.3 0 2.3 1 2.3 2.3V17" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg></a></nav></div></header>""",
        ticker,
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
        """<footer style="background:#fff;border-top:1px solid #e5e7eb;padding:14px 24px;text-align:center;font:400 11.5px Inter,'Segoe UI',system-ui,sans-serif;color:#8b909c;flex-shrink:0">&copy; 2026 Arash Nassirpour</footer>""",
        '<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>',
        "<script>" + js + "</script>",
        "</body></html>",
    ])
