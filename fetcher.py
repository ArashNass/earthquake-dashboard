# fetcher.py - All HTTP data fetching. Enrichment lives in engine.py; USGS product parsing in usgs_products.py.

import html as _html
import json
import math
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta, date
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus

import requests
from requests.adapters import HTTPAdapter, Retry

import usgs_products as U
from settings import (US_STATES, REGION_WORDS, SSL, HTTP_TIMEOUT, HTTP_RETRIES,
                      USER_AGENT, QUERY_DAYS, QUERY_LIMIT, QUERY_MIN_MAG)
from engine import enrich  # re-exported for run.py

__all__ = ["fetch_top_events", "fetch_detail", "enrich", "extract_shakemap",
           "extract_aftershock", "extract_focal", "fetch_historical",
           "fetch_weather", "fetch_general_links", "fetch_media_links", "fetch_ai",
           "get_country"]

if not SSL:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ── Shared session with retries ───────────────────────────────────────────────

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
_retry = Retry(total=HTTP_RETRIES, backoff_factor=0.4,
               status_forcelist=(500, 502, 503, 504),
               allowed_methods=("GET", "POST"))
_session.mount("https://", HTTPAdapter(max_retries=_retry))
_session.mount("http://",  HTTPAdapter(max_retries=_retry))


def get(url, timeout=HTTP_TIMEOUT, **kw):
    return _session.get(url, timeout=timeout, verify=SSL, **kw)


def post(url, timeout=HTTP_TIMEOUT, **kw):
    return _session.post(url, timeout=timeout, verify=SSL, **kw)

# ── Place and time helpers ────────────────────────────────────────────────────

def get_country(place):
    """Country (or the last place component) from a USGS place string."""
    parts = [p.strip() for p in (place or "").split(",")]
    last  = parts[-1] if parts else ""
    if last in US_STATES:
        return "United States"
    if any(w in last.lower() for w in REGION_WORDS) and len(parts) >= 2:
        return parts[-2]
    return last


def _km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def _event_dt(ev):
    for key, fmt in (("t_utc", "%Y-%m-%dT%H:%M:%S"), ("t_iso", "%Y-%m-%d")):
        try:
            return datetime.strptime(ev.get(key) or "", fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None

# ── USGS ──────────────────────────────────────────────────────────────────────

def fetch_top_events(days=QUERY_DAYS, limit=QUERY_LIMIT, min_mag=QUERY_MIN_MAG):
    start = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    r = get(f"https://earthquake.usgs.gov/fdsnws/event/1/query"
            f"?format=geojson&starttime={start}&minmagnitude={min_mag}"
            f"&orderby=magnitude&limit={limit}")
    r.raise_for_status()
    events = []
    for f in r.json().get("features", []):
        p = f.get("properties") or {}
        c = (f.get("geometry") or {}).get("coordinates") or [0, 0, 0]
        t = datetime.fromtimestamp((p.get("time") or 0) / 1000, tz=timezone.utc)
        events.append({
            "id":           f.get("id", ""),
            "mag":          float(p.get("mag") or 0),
            "place":        p.get("place") or "Unknown location",
            "time_str":     t.strftime("%d %b %Y %H:%M UTC"),
            "t_ms":         int(p.get("time") or 0),
            "alert":        (p.get("alert") or "").upper(),
            "tsunami":      bool(p.get("tsunami")),
            "lat":          float(c[1]),
            "lon":          float(c[0]),
            "depth":        float(c[2]),
            "has_shakemap": bool((p.get("products") or {}).get("shakemap")),
            "url":          p.get("url", ""),
            "_time":        t,
        })
    # USGS picks the largest events; show them newest first.
    events.sort(key=lambda e: e["_time"], reverse=True)
    for e in events:
        del e["_time"]
    return events


def fetch_detail(eid):
    r = get(f"https://earthquake.usgs.gov/fdsnws/event/1/query"
            f"?format=geojson&eventid={eid}")
    r.raise_for_status()
    return r.json()


def extract_shakemap(detail):
    """ShakeMap contour URLs and the published peak ground motions (see usgs_products.shakemap)."""
    return U.shakemap(detail) or {"mmi_url": "", "pga_url": "", "peak": None, "version": None,
                                  "status": None, "processed": None}


def extract_aftershock(detail):
    try:
        return U.aftershock_forecast(detail, get)
    except Exception:
        return None


def extract_focal(detail):
    return U.moment_tensor(detail)


def fetch_historical(lat, lon, eid, before_iso=None, radius_km=250):
    """M5.5+ events within radius_km over the last 100 years, excluding the current event
    and (via before_iso) its own aftershock sequence. Largest first."""
    try:
        end = before_iso or date.today().isoformat()
        feats = get(
            f"https://earthquake.usgs.gov/fdsnws/event/1/query"
            f"?format=geojson"
            f"&starttime={date.today().year - 100}-01-01"
            f"&endtime={end}"
            f"&latitude={lat}&longitude={lon}"
            f"&maxradiuskm={radius_km}&minmagnitude=5.5"
            f"&orderby=magnitude&limit=8"
        ).json().get("features", [])
        out = []
        for f in feats:
            if f.get("id") == eid:
                continue
            p = f.get("properties") or {}
            c = (f.get("geometry") or {}).get("coordinates") or [0, 0, 0]
            t = datetime.fromtimestamp((p.get("time") or 0) / 1000, tz=timezone.utc)
            out.append({"mag": p.get("mag", 0), "place": p.get("place", ""),
                        "year": t.year, "month": t.strftime("%b"),
                        "dist_km": round(_km(lat, lon, c[1], c[0])),
                        "url": p.get("url", "")})
        return out[:5]
    except Exception:
        return []


def fetch_weather(lat, lon):
    """Rainfall over the three days before the event day (Open-Meteo). A plain measurement:
    no landslide score is derived from it."""
    try:
        d = get(
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&daily=precipitation_sum"
            f"&past_days=3&forecast_days=1&timezone=auto",
            timeout=10
        ).json()
        daily = (d.get("daily", {}) or {}).get("precipitation_sum") or []
        vals = [v for v in daily[:3] if v is not None]
        if not vals:
            return None
        return {"precip_3day_mm": round(sum(vals), 1)}
    except Exception:
        return None

# ── Links: Wikipedia, USGS, EMSC, GDACS, ReliefWeb, GEM ───────────────────────

def _wiki_matches(extract, mag, dt):
    """Accept a Wikipedia summary only if it describes THIS event: same year and month, a day
    within +/-1 of the event, and a stated magnitude within 0.5."""
    if not extract or dt is None or str(dt.year) not in extract:
        return False
    month = dt.strftime("%B")
    days = {int(d) for d in re.findall(r"\b(\d{1,2})\s+" + month + r"\b", extract)}
    days |= {int(d) for d in re.findall(month + r"\s+(\d{1,2})\b", extract)}
    if not any(abs(d - dt.day) <= 1 for d in days):
        return False
    mags = [float(x) for x in re.findall(r"(?:Mw[wsb]?|Mww|\bM|magnitude)\s*(\d\.\d)", extract)]
    return any(abs(m - mag) <= 0.5 for m in mags)


def _find_wikipedia(ev, country, dt):
    """(title, url) of the Wikipedia article about this earthquake, or None."""
    year = str(dt.year) if dt else str(datetime.now(timezone.utc).year)
    c = country.replace(" ", "_")
    titles = [f"{year}_{c}_earthquake", f"{year}_{c}_earthquakes"]
    try:
        r2 = get("https://en.wikipedia.org/w/api.php",
                 params={"action": "opensearch", "search": f"{year} {country} earthquake",
                         "limit": 5, "format": "json"}, timeout=8)
        if r2.status_code == 200:
            titles += [t.replace(" ", "_") for t in r2.json()[1]]
    except Exception:
        pass
    seen = set()
    for title in titles:
        if title in seen:
            continue
        seen.add(title)
        try:
            r = get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}", timeout=8)
            if r.status_code != 200:
                continue
            d = r.json()
            if len(d.get("extract", "")) > 60 and _wiki_matches(d["extract"], float(ev["mag"]), dt):
                url = d.get("content_urls", {}).get("desktop", {}).get("page", "")
                if url:
                    return d.get("title", ""), url
        except Exception:
            continue
    return None


def _find_gdacs(ev, dt):
    """URL of the GDACS report for this earthquake (matched by place, time and magnitude)."""
    if not dt:
        return None
    lat, lon, mag = float(ev["lat"]), float(ev["lon"]), float(ev["mag"])
    try:
        r = get("https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
                f"?eventlist=EQ&fromdate={(dt - timedelta(days=1)).date()}&todate={(dt + timedelta(days=1)).date()}"
                "&alertlevel=green;orange;red", timeout=15)
        best = None
        for f in r.json().get("features", []):
            fp = f.get("properties") or {}
            c = (f.get("geometry") or {}).get("coordinates") or []
            try:
                fdt = datetime.strptime(fp.get("fromdate", ""), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
                sev = float((fp.get("severitydata") or {}).get("severity"))
                d = _km(lat, lon, c[1], c[0])
            except (TypeError, ValueError, IndexError):
                continue
            if d <= 150 and abs(sev - mag) <= 0.6 and abs((fdt - dt).total_seconds()) <= 10800:
                if best is None or d < best[0]:
                    best = (d, (fp.get("url") or {}).get("report", ""))
        return best[1] if best and best[1] else None
    except Exception:
        return None


def _find_emsc(ev, dt):
    """URL of the EMSC event page for this earthquake."""
    if not dt:
        return None
    lat, lon, mag = float(ev["lat"]), float(ev["lon"]), float(ev["mag"])
    try:
        t0, t1 = ((dt - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S"),
                  (dt + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S"))
        r = get("https://www.seismicportal.eu/fdsnws/event/1/query?format=json"
                f"&starttime={t0}&endtime={t1}&lat={lat}&lon={lon}&maxradius=1.5"
                f"&minmag={max(2.0, mag - 1.5)}&limit=10", timeout=12)
        best = None
        for f in r.json().get("features", []):
            fp = f.get("properties") or {}
            try:
                score = abs(float(fp["mag"]) - mag)
            except (KeyError, TypeError, ValueError):
                continue
            if fp.get("unid") and (best is None or score < best[0]):
                best = (score, fp["unid"])
        if best and best[0] <= 1.0:
            return f"https://www.seismicportal.eu/eventdetails.html?unid={best[1]}"
    except Exception:
        pass
    return None


def _gem_url(eid):
    url = f"https://www.globalquakemodel.org/post-event-info/{eid}"
    try:
        return url if get(url, timeout=10).status_code == 200 else None
    except Exception:
        return None


def fetch_general_links(ev, detail):
    """General reference links for the event, as [{title, url}]: one short title each.
    Event-specific pages (Wikipedia article, EMSC, GDACS, GEM) appear only when they exist."""
    dt = _event_dt(ev)
    country = get_country(ev["place"]) or ev["place"]
    year = dt.year if dt else datetime.now(timezone.utc).year
    eid = ev["event_id"]
    base = ev.get("url") or f"https://earthquake.usgs.gov/earthquakes/eventpage/{eid}"
    res = {}

    def run(key, fn):
        try:
            res[key] = fn()
        except Exception:
            res[key] = None

    threads = [threading.Thread(target=run, args=(k, fn), daemon=True) for k, fn in (
        ("wiki", lambda: _find_wikipedia(ev, country, dt)),
        ("gdacs", lambda: _find_gdacs(ev, dt)),
        ("emsc", lambda: _find_emsc(ev, dt)),
        ("gem", lambda: _gem_url(eid)),
    )]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    links = []
    if res.get("wiki"):
        links.append({"title": f"Wikipedia — {res['wiki'][0]}", "url": res["wiki"][1]})
    else:
        links.append({"title": f"Wikipedia — Search: {year} {country} earthquake",
                      "url": f"https://en.wikipedia.org/w/index.php?search={quote_plus(f'{year} {country} earthquake')}"})
    links.append({"title": f"Wikipedia — List of earthquakes in {year}",
                  "url": f"https://en.wikipedia.org/wiki/List_of_earthquakes_in_{year}"})
    links.append({"title": "USGS — Event page", "url": base})
    if product_present(detail, "losspager"):
        links.append({"title": "USGS — PAGER impact estimate", "url": base + "/pager"})
    if product_present(detail, "shakemap"):
        links.append({"title": "USGS — ShakeMap", "url": base + "/shakemap"})
    if res.get("emsc"):
        links.append({"title": "EMSC — Event report", "url": res["emsc"]})
    if res.get("gdacs"):
        links.append({"title": "GDACS — Alert report", "url": res["gdacs"]})
    links.append({"title": f"ReliefWeb — Earthquake updates: {country}",
                  "url": f"https://reliefweb.int/updates?search={quote_plus('earthquake ' + country)}"})
    if res.get("gem"):
        links.append({"title": "GEM Foundation — Post-event assessment", "url": res["gem"]})
    if ev.get("tsunami"):
        links.append({"title": "NOAA — Tsunami messages (tsunami.gov)", "url": "https://www.tsunami.gov"})
    return links


def product_present(detail, name):
    return U.product(detail, name) is not None

# ── Links: media coverage (BBC, CNN, Sky News, ABC) ───────────────────────────

# Coverage is found with Google News RSS searches restricted to each outlet. The feed gives the
# article headline and a link; nothing is scraped or copied. When no matching article is found
# the row links to that outlet's own search page instead.
OUTLETS = [
    {"name": "BBC News", "domains": ("bbc.com", "bbc.co.uk"), "site": "(site:bbc.com OR site:bbc.co.uk)",
     "hl": ("en-GB", "GB", "GB:en"), "search": "https://www.bbc.co.uk/search?q={q}"},
    {"name": "CNN", "domains": ("cnn.com",), "site": "site:cnn.com",
     "hl": ("en-US", "US", "US:en"), "search": "https://edition.cnn.com/search?q={q}&types=article"},
    {"name": "Sky News", "domains": ("news.sky.com", "sky.com"), "site": "site:news.sky.com",
     "hl": ("en-GB", "GB", "GB:en"), "search": "https://news.sky.com/search?term={q}"},
    {"name": "ABC News", "domains": ("abcnews.go.com", "abcnews.com", "abc.net.au"),
     "site": "(site:abcnews.go.com OR site:abc.net.au)",
     "hl": ("en-US", "US", "US:en"), "search": "https://abcnews.go.com/search?searchtext={q}"},
]
_QUAKE_WORDS = ("earthquake", "quake", "tremor", "temblor", "seismic")
_MEDIA_CACHE = Path(__file__).resolve().parent / "media_cache.json"
_media_lock = threading.Lock()
_MEDIA_TTL_OK, _MEDIA_TTL_PARTIAL = 4 * 3600, 20 * 60


def _media_cache_get(eid):
    try:
        with _media_lock:
            return json.loads(_MEDIA_CACHE.read_text("utf-8")).get(eid)
    except Exception:
        return None


def _media_cache_put(eid, items, complete):
    try:
        with _media_lock:
            try:
                data = json.loads(_MEDIA_CACHE.read_text("utf-8"))
            except Exception:
                data = {}
            data[eid] = {"t": time.time(), "complete": complete, "items": items}
            data = {k: v for k, v in data.items() if time.time() - v.get("t", 0) < 3 * 86400}
            _MEDIA_CACHE.write_text(json.dumps(data), "utf-8")
    except Exception:
        pass


def _parse_news_rss(content):
    """Items of a Google News RSS feed: title (outlet suffix removed), link, outlet host, date."""
    out = []
    root = ET.fromstring(content)
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src = it.find("source")
        sname = ((src.text or "") if src is not None else "").strip()
        surl = (src.get("url", "") if src is not None else "")
        host = re.sub(r"^https?://(www\.)?", "", surl).split("/")[0].lower()
        if sname and title.endswith(" - " + sname):
            title = title[: -len(sname) - 3].rstrip()
        try:
            pub = parsedate_to_datetime(it.findtext("pubDate") or "")
        except (TypeError, ValueError):
            pub = None
        if title and link:
            out.append({"title": _html.unescape(title), "url": link, "host": host, "pub": pub})
    return out


def _relevant(item, outlet, ev, country, dt):
    """A headline counts only if it is from this outlet, about an earthquake in this place or of
    this size, and published in the weeks after the event."""
    host = item["host"]
    if not any(host == d or host.endswith("." + d) for d in outlet["domains"]):
        return False
    tl = item["title"].lower()
    if not any(w in tl for w in _QUAKE_WORDS):
        return False
    mag_s = f"{float(ev['mag']):.1f}"
    place_words = [w.lower() for w in re.split(r"[,\s]+", ev["place"]) if len(w) > 4 and w.lower() != (country or "").lower() and w.lower() not in ("north", "south", "east", "west", "northern", "southern", "eastern", "western")]
    stated = [float(m) for m in re.findall(r"(?<![\d.])([5-9]\.\d)(?![\d])", tl)]
    if stated and not any(abs(m - float(ev["mag"])) <= 0.4 for m in stated):
        return False        # the headline gives a magnitude, and it is a different earthquake
    country_ok = bool(country and country.lower() in tl) and not ev.get("country_shared")
    if not (country_ok or mag_s in tl or any(w in tl for w in place_words[-2:])):
        return False
    if dt and item["pub"]:
        delta = item["pub"] - dt
        if delta < timedelta(hours=-1) or delta > timedelta(days=21):
            return False
    return True


def fetch_media_links(ev):
    """One row per outlet: [{outlet, title, url, kind}], kind 'article' (a matching headline) or 'search'.
    Results are cached per event so the hourly rebuild stays polite to Google News."""
    eid = ev["event_id"]
    cached = _media_cache_get(eid)
    if cached:
        ttl = _MEDIA_TTL_OK if cached.get("complete") else _MEDIA_TTL_PARTIAL
        if time.time() - cached.get("t", 0) < ttl:
            return cached.get("items") or []

    dt = _event_dt(ev)
    country = get_country(ev["place"]) or ev["place"]
    d0 = ((dt or datetime.now(timezone.utc)) - timedelta(days=1)).strftime("%Y-%m-%d")
    d1 = ((dt or datetime.now(timezone.utc)) + timedelta(days=21)).strftime("%Y-%m-%d")
    complete = True
    rows = []
    for outlet in OUTLETS:
        hl, gl, ceid = outlet["hl"]
        found = None
        queries = [f'earthquake {country} {outlet["site"]} after:{d0} before:{d1}',
                   f'earthquake {country} "{outlet["name"]}" after:{d0} before:{d1}']
        for q in queries:
            try:
                r = get("https://news.google.com/rss/search", params={"q": q, "hl": hl, "gl": gl, "ceid": ceid}, timeout=12)
                if r.status_code != 200:
                    complete = False
                    continue
                for item in _parse_news_rss(r.content):
                    if _relevant(item, outlet, ev, country, dt):
                        found = item
                        break
            except Exception:
                complete = False
            time.sleep(0.25)
            if found:
                break
        if found:
            rows.append({"outlet": outlet["name"], "title": found["title"], "url": found["url"], "kind": "article"})
        else:
            rows.append({"outlet": outlet["name"], "title": "Search coverage of this earthquake", "kind": "search",
                         "url": outlet["search"].format(q=quote_plus(f"earthquake {country}"))})
    _media_cache_put(eid, rows, complete)
    if not complete and cached and cached.get("items"):
        return cached["items"]
    return rows

# ── AI narrative (optional) ───────────────────────────────────────────────────

def fetch_ai(ev, pager=None, foc=None, sm=None):
    """3-sentence analyst narrative via the Anthropic API.
    Requires ANTHROPIC_API_KEY in the environment; returns None otherwise."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        peak = (sm or {}).get("peak") or {}
        lines = [
            f"M{ev['mag']:.1f} - {ev['place']}",
            f"Depth: {ev['depth']:.0f} km ({ev['depth_note']})",
            f"ShakeMap peak: MMI {peak.get('mmi')}, PGA {peak.get('pga_g')} g, PGV {peak.get('pgv_cms')} cm/s",
        ]
        if pager:
            fat, eco = pager.get("fatality") or {}, pager.get("economic") or {}
            lines.append(f"USGS PAGER alerts: fatalities {fat.get('level')}, economic {eco.get('level')}")
        if foc:
            lines.append(f"Mechanism: {foc.get('type')}")
        r = post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-5-5",
                "max_tokens": 320,
                "system": ("You are a senior reinsurance technical analyst. "
                           "Write exactly 3 sentences covering: (1) tectonic context and loss drivers, "
                           "(2) primary risk to insured portfolio, (3) key uncertainties. "
                           "Be precise and use only the figures given. No bullet points."),
                "messages": [{"role": "user", "content": "\n".join(lines)}],
            },
            timeout=25)
        r.raise_for_status()
        blocks = r.json().get("content", [])
        text = " ".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        return text or None
    except Exception:
        return None
