# fetcher.py - All HTTP data fetching. Enrichment lives in engine.py.

import json
import math
import os
import re
import threading
import time
import html as _html
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter, Retry

from settings import (BUILDING_STOCK, US_STATES, REGION_WORDS,
                      NEWS_SOURCE_ORDER, SSL, HTTP_TIMEOUT, HTTP_RETRIES,
                      USER_AGENT, QUERY_DAYS, QUERY_LIMIT, QUERY_MIN_MAG)
from engine import enrich, mmi_to_pga_pctg  # re-exported for run.py

__all__ = ["fetch_top_events", "fetch_detail", "enrich", "extract_shakemap",
           "extract_aftershock", "extract_focal", "fetch_historical",
           "fetch_weather", "fetch_news", "fetch_headlines", "fetch_intel", "fetch_ai",
           "get_building_stock", "get_country"]

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

# ── Place helpers ─────────────────────────────────────────────────────────────

def get_country(place):
    parts = [p.strip() for p in (place or "").split(",")]
    last  = parts[-1] if parts else ""
    if last in US_STATES:
        return "United States"
    if any(w in last.lower() for w in REGION_WORDS) and len(parts) >= 2:
        return parts[-2]
    return last


def get_building_stock(place):
    place_l = (place or "").lower()
    if get_country(place) == "United States":
        return BUILDING_STOCK["United States"]
    for k, v in BUILDING_STOCK.items():
        if k != "DEFAULT" and k.lower() in place_l:
            return v
    return BUILDING_STOCK["DEFAULT"]

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
        h = (datetime.now(timezone.utc) - t).total_seconds() / 3600
        events.append({
            "id":           f.get("id", ""),
            "mag":          float(p.get("mag") or 0),
            "place":        p.get("place") or "Unknown location",
            "time_str":     t.strftime("%d %b %Y %H:%M UTC"),
            "age_str":      f"{int(h)}h ago" if h < 48 else f"{int(h / 24)}d ago",
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
    r = {"mmi_url": "", "pga_url": ""}
    try:
        sm = detail["properties"]["products"].get("shakemap", [])
        if sm:
            cx = sm[0].get("contents", {}) or {}
            r["mmi_url"] = cx.get("download/cont_mmi.json", {}).get("url", "")
            r["pga_url"] = cx.get("download/cont_pga.json", {}).get("url", "")
    except (KeyError, TypeError, IndexError):
        pass
    return r


def extract_aftershock(detail):
    try:
        oaf = detail["properties"]["products"].get("oaf", [])
        if not oaf:
            return None
        fe = (oaf[0].get("contents", {}) or {}).get("forecast.json", {})
        if not fe.get("url"):
            return None
        fc = get(fe["url"], timeout=12).json()
        bins = []
        for row in fc.get("forecast", []):
            m = row.get("magnitude", 0)
            if m in (5, 6, 7):
                bins.append({
                    "mag":      m,
                    "p_1day":   (row.get("oneDay")   or {}).get("probability", "?"),
                    "p_1week":  (row.get("oneWeek")  or {}).get("probability", "?"),
                    "p_1month": (row.get("oneMonth") or {}).get("probability", "?"),
                    "n_1week":  (row.get("oneWeek")  or {}).get("median", "?"),
                })
        model = (fc.get("model") or {}).get("name", "Reasenberg-Jones")
        return {"model": model, "bins": bins} if bins else None
    except Exception:
        return None


def extract_focal(detail):
    products = (detail.get("properties") or {}).get("products") or {}
    for key in ("moment-tensor", "focal-mechanism"):
        mt = products.get(key, [])
        if not mt:
            continue
        props = mt[0].get("properties", {}) or {}
        rake = props.get("nodal-plane-1-rake", "")
        try:
            r = float(rake) % 360
        except (TypeError, ValueError):
            continue  # try the next product instead of bailing out entirely
        if r > 180:
            r -= 360
        ft = ("Strike-Slip"      if (-30 <= r <= 30 or abs(r) >= 150) else
              "Reverse / Thrust" if   60 <= r <= 120                  else
              "Normal"           if -120 <= r <= -60                  else
              "Oblique Reverse"  if   30 <  r <   60                  else
              "Oblique Normal")
        return {
            "type":   ft,
            "strike": props.get("nodal-plane-1-strike", ""),
            "dip":    props.get("nodal-plane-1-dip", ""),
            "rake":   rake,
        }
    return None


def fetch_historical(lat, lon, eid, before_iso=None, radius_km=250):
    """M5.5+ events within radius_km over the last 100 years, excluding the
    current event and (via before_iso) its own aftershock sequence."""
    try:
        end = before_iso or date.today().isoformat()
        feats = get(
            f"https://earthquake.usgs.gov/fdsnws/event/1/query"
            f"?format=geojson"
            f"&starttime={date.today().year - 100}-01-01"
            f"&endtime={end}"
            f"&latitude={lat}&longitude={lon}"
            f"&maxradiuskm={radius_km}&minmagnitude=5.5"
            f"&orderby=magnitude&limit=6"
        ).json().get("features", [])
        out = []
        for f in feats:
            if f.get("id") == eid:
                continue
            p = f.get("properties") or {}
            t = datetime.fromtimestamp((p.get("time") or 0) / 1000, tz=timezone.utc)
            out.append({"mag": p.get("mag", 0), "place": p.get("place", ""),
                        "year": t.year, "url": p.get("url", "")})
        return out[:5]
    except Exception:
        return []


def fetch_weather(lat, lon):
    """Recent (past 3 days) rainfall drives landslide risk, not the forecast."""
    try:
        d = get(
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m&daily=precipitation_sum"
            f"&past_days=3&forecast_days=1&timezone=auto",
            timeout=10
        ).json()
        daily = (d.get("daily", {}) or {}).get("precipitation_sum") or []
        rain3 = sum(v for v in daily[:3] if v is not None)
        risk  = "High" if rain3 > 50 else "Moderate" if rain3 > 20 else "Low"
        return {
            "temp_c":         round(d["current"]["temperature_2m"], 1),
            "precip_3day_mm": round(rain3, 1),
            "landslide_risk": risk,
        }
    except Exception:
        return None

# ── Intelligence ──────────────────────────────────────────────────────────────
# Two parts, both keyless:
#   fetch_intel     - verified event facts (USGS record, aftershocks, GDACS, EMSC cross-check)
#   fetch_news      - reports about *this* event (GEM, ReliefWeb, validated Wikipedia)
#   fetch_headlines - recent news headlines (GDELT, rate-limited to 1 request / 5 s)

def _km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def _event_dt(ev):
    try:
        return datetime.strptime(ev.get("t_utc") or "", "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    try:
        return datetime.strptime(ev.get("t_iso") or "", "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _wiki_matches(extract, mag, dt):
    """Accept a Wikipedia summary only if it describes THIS event: same year and month,
    a day within +/-1 of the event, and a stated magnitude within 0.5."""
    if not extract or dt is None or str(dt.year) not in extract:
        return False
    month = dt.strftime("%B")
    days = {int(d) for d in re.findall(r"\b(\d{1,2})\s+" + month + r"\b", extract)}
    days |= {int(d) for d in re.findall(month + r"\s+(\d{1,2})\b", extract)}
    if not any(abs(d - dt.day) <= 1 for d in days):
        return False
    mags = [float(x) for x in re.findall(r"(?:Mw[wsb]?|Mww|\bM|magnitude)\s*(\d\.\d)", extract)]
    return any(abs(m - mag) <= 0.5 for m in mags)


def fetch_news(ev):
    """Reports about this specific event. No API keys needed. Items that cannot be
    tied to the event (wrong year, month or magnitude) are dropped, never shown."""
    news = []
    lock = threading.Lock()

    eid      = ev["event_id"]
    mag      = ev["mag"]
    place    = ev["place"]
    country  = get_country(place)
    dt       = _event_dt(ev)
    year     = str(dt.year) if dt else str(datetime.now(timezone.utc).year)
    event_dt = ev.get("t_iso") or date.today().isoformat()

    def add(item):
        if item and isinstance(item, dict) and item.get("headline"):
            with lock:
                news.append(item)

    # 1. GEM Foundation post-event assessment (exists only for major events)
    def _gem():
        try:
            r = get(f"https://www.globalquakemodel.org/post-event-info/{eid}", timeout=10)
            if r.status_code != 200:
                return
            text = r.text
            m = (re.search(r'<meta[^>]+property=["\']og:description["\'][^>]+content="([^"]{40,})"', text)
                 or re.search(r'<meta[^>]+content="([^"]{40,})"[^>]+property=["\']og:description["\']', text))
            if m:
                summary = re.sub(r'\s*\(Source:.*$', '', m.group(1).strip())
                if len(summary) > 40:
                    add({"source": "GEM Foundation",
                         "headline": f"Post-Event Assessment: M{mag} {country}",
                         "summary": summary[:300],
                         "url": f"https://www.globalquakemodel.org/post-event-info/{eid}"})
        except Exception:
            pass

    # 2. ReliefWeb (needs an approved appname since 2025; quietly yields nothing without one)
    def _reliefweb():
        try:
            appname = os.environ.get("RELIEFWEB_APPNAME", "eq-dashboard")
            payload = {
                "query": {"value": "earthquake"},
                "filter": {"operator": "AND", "conditions": [
                    {"field": "primary_country.name", "value": country},
                    {"field": "date.created", "value": {"from": event_dt + "T00:00:00+00:00"}},
                ]},
                "fields": {"include": ["title", "url", "source.name", "body"]},
                "sort": [{"field": "date", "direction": "desc"}],
                "limit": 3,
            }
            r = post(f"https://api.reliefweb.int/v2/reports?appname={appname}", json=payload, timeout=12)
            if r.status_code != 200:
                return
            for item in r.json().get("data", []):
                f     = item.get("fields", {})
                srcs  = f.get("source", [{}])
                src   = srcs[0].get("name", "UN ReliefWeb") if srcs else "UN ReliefWeb"
                title = f.get("title", "")
                body  = re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', f.get("body", ""))).strip()[:250]
                rw_id = item.get("id", "")
                url   = f.get("url", "") or f"https://reliefweb.int/node/{rw_id}"
                if title:
                    add({"source": src, "headline": title[:120], "summary": body, "url": url})
        except Exception:
            pass

    # 3. Wikipedia - only an article that matches this event's date and magnitude
    def _wikipedia():
        try:
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
                r = get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}", timeout=8)
                if r.status_code != 200:
                    continue
                d = r.json()
                extract = d.get("extract", "")
                if len(extract) > 60 and _wiki_matches(extract, float(mag), dt):
                    sentences = extract.split(". ")
                    summary = ". ".join(sentences[:2]).strip()
                    if not summary.endswith("."):
                        summary += "."
                    add({"source": "Wikipedia", "headline": d.get("title", ""), "summary": summary[:300],
                         "url": d.get("content_urls", {}).get("desktop", {}).get("page", "")})
                    return
        except Exception:
            pass

    threads = [threading.Thread(target=fn, daemon=True) for fn in (_gem, _reliefweb, _wikipedia)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    news.sort(key=lambda x: next(
        (i for i, s in enumerate(NEWS_SOURCE_ORDER) if s == x["source"]), 99))
    return news[:4]


_gdelt_lock = threading.Lock()
_gdelt_last = [0.0]
_gdelt_t0 = [0.0]
_QUAKE_WORDS = ("earthquake", "quake", "tremor", "seismic", "temblor", "sismo", "terremoto")
_CACHE_FILE = Path(__file__).resolve().parent / "headlines_cache.json"
_cache_lock = threading.Lock()
_CACHE_OK_TTL, _CACHE_FAIL_TTL = 6 * 3600, 30 * 60


def _cache_get(eid):
    try:
        with _cache_lock:
            return json.loads(_CACHE_FILE.read_text("utf-8")).get(eid)
    except Exception:
        return None


def _cache_put(eid, items, ok):
    try:
        with _cache_lock:
            try:
                data = json.loads(_CACHE_FILE.read_text("utf-8"))
            except Exception:
                data = {}
            data[eid] = {"t": time.time(), "ok": ok, "items": items}
            # keep the file small: drop entries older than 4 days
            data = {k: v for k, v in data.items() if time.time() - v.get("t", 0) < 4 * 86400}
            _CACHE_FILE.write_text(json.dumps(data), "utf-8")
    except Exception:
        pass


def fetch_headlines(ev):
    """Up to 3 recent news headlines about this earthquake from GDELT (free, no key).
    GDELT allows one request every 5 seconds and throttles shared IPs hard, so results are
    cached per event (6 h; 30 min after a failed call) and a failure never breaks the build."""
    dt = _event_dt(ev)
    country = get_country(ev["place"])
    eid = ev.get("event_id", "")
    if not dt or not country:
        return []
    if (datetime.now(timezone.utc) - dt).days > 80:   # GDELT's news index only covers ~3 months
        return []

    cached = _cache_get(eid)
    if cached:
        ttl = _CACHE_OK_TTL if cached.get("ok") else _CACHE_FAIL_TTL
        if time.time() - cached.get("t", 0) < ttl:
            return cached.get("items") or []

    params = {"query": f'earthquake "{country}" sourcelang:english', "mode": "artlist", "format": "json",
              "maxrecords": 15, "sort": "hybridrel", "startdatetime": dt.strftime("%Y%m%d%H%M%S")}
    data = None
    with _gdelt_lock:
        if not _gdelt_t0[0]:
            _gdelt_t0[0] = time.time()
        if time.time() - _gdelt_t0[0] > 75:   # queue budget: never hold the build up for headlines
            return (cached or {}).get("items") or []
        wait = 5.6 - (time.time() - _gdelt_last[0])
        if wait > 0:
            time.sleep(wait)
        _gdelt_last[0] = time.time()
        try:
            r = get("https://api.gdeltproject.org/api/v2/doc/doc", params=params, timeout=12)
            if r.status_code == 200:
                data = r.json()
        except Exception:
            data = None
    if data is None:                       # throttled / unreachable: remember, keep any older result
        _cache_put(eid, (cached or {}).get("items") or [], ok=False)
        return (cached or {}).get("items") or []

    out, seen = [], set()
    mag_s = f"{float(ev['mag']):.1f}"
    for a in data.get("articles", []):
        title = _html.unescape((a.get("title") or "").strip())
        tl = title.lower()
        key = re.sub(r"\W+", "", tl)[:40]
        if (not title or key in seen or not any(w in tl for w in _QUAKE_WORDS)
                or not (country.lower() in tl or mag_s in tl)):
            continue
        seen.add(key)
        sd = a.get("seendate", "")
        when = f"{sd[6:8]}/{sd[4:6]}/{sd[:4]}" if len(sd) >= 8 else ""
        out.append({"source": a.get("domain", "news"), "headline": title[:140],
                    "summary": ("Published " + when) if when else "", "url": a.get("url", "")})
        if len(out) == 3:
            break
    _cache_put(eid, out, ok=True)
    return out


def fetch_intel(ev, detail):
    """Verified, event-specific facts. Each fact: {label, value, tone, url}. tone is
    ok / info / warn / alert. Anything that cannot be confirmed is simply omitted."""
    dt = _event_dt(ev)
    mag, lat, lon = float(ev["mag"]), float(ev["lat"]), float(ev["lon"])
    p = (detail or {}).get("properties") or {}
    prods = p.get("products") or {}
    res = {}

    def run(key, fn):
        try:
            res[key] = fn()
        except Exception:
            res[key] = None

    def usgs_review():
        st = (p.get("status") or "").lower()
        if st == "reviewed":
            return {"label": "USGS solution", "value": "Reviewed by a seismologist", "tone": "ok"}
        if st:
            return {"label": "USGS solution", "value": "Automatic - may be revised", "tone": "warn"}

    def felt():
        n, cdi = int(p.get("felt") or 0), p.get("cdi")
        if n:
            tail = f" - max intensity {float(cdi):.1f}" if cdi else ""
            return {"label": "Felt reports", "value": f"{n:,} 'Did You Feel It'{tail}", "tone": "info",
                    "url": ev.get("url", "") and ev["url"] + "/dyfi"}
        return {"label": "Felt reports", "value": "None submitted yet", "tone": "info"}

    def model_products():
        names = [("shakemap", "ShakeMap"), ("losspager", "PAGER"), ("moment-tensor", "Moment tensor"),
                 ("finite-fault", "Finite fault"), ("ground-failure", "Ground failure")]
        have = [lbl for key, lbl in names if prods.get(key)]
        if have:
            return {"label": "USGS products", "value": " - ".join(have), "tone": "info", "url": ev.get("url", "")}

    def aftershocks():
        if not dt:
            return None
        start = (dt + timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%S")
        base = (f"?format=geojson&starttime={start}&latitude={lat}&longitude={lon}"
                f"&maxradiuskm=150&minmagnitude=2.5")
        n = int(get("https://earthquake.usgs.gov/fdsnws/event/1/count" + base, timeout=12).json().get("count", 0))
        if n == 0:
            return {"label": "Aftershocks", "value": "None recorded (M2.5+, within 150 km)", "tone": "info"}
        top = get("https://earthquake.usgs.gov/fdsnws/event/1/query" + base + "&orderby=magnitude&limit=1",
                  timeout=12).json().get("features", [])
        big = float((top[0]["properties"].get("mag") if top else 0) or 0)
        tone = "warn" if big >= mag - 1.2 else "info"
        return {"label": "Aftershocks", "value": f"{n:,} so far (M2.5+, within 150 km) - largest M{big:.1f}", "tone": tone}

    def gdacs():
        if not dt:
            return None
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
                    best = (d, fp)
        if not best:
            return None
        fp = best[1]
        level = (fp.get("alertlevel") or "").title()
        out = [{"label": "UN GDACS alert", "value": f"{level} - impact estimate", "tone":
                {"Red": "alert", "Orange": "warn", "Green": "ok"}.get(level, "info"),
                "url": (fp.get("url") or {}).get("report", "")}]
        try:
            d2 = get("https://www.gdacs.org/gdacsapi/api/events/geteventdata?eventtype=EQ"
                     f"&eventid={fp.get('eventid')}", timeout=15).json()
            q = (((d2.get("features") or [{}])[0].get("properties")) or d2.get("properties") or {}).get("earthquakedetails") or {}
            pop = (q.get("shakepopdescription") or "").strip()
            if pop and not pop.startswith("0"):
                out.append({"label": "Population exposed", "value": pop.replace(">=", "≥"), "tone": "warn"
                            if level in ("Orange", "Red") else "info"})
            ts = float(q.get("tsmaxheight") or 0)
            if ts >= 0.3:
                out.append({"label": "Modelled tsunami", "value": f"Up to ~{ts:.1f} m wave height", "tone": "warn"})
        except Exception:
            pass
        return out

    def emsc():
        if not dt:
            return None
        t0, t1 = (dt - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S"), (dt + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")
        r = get("https://www.seismicportal.eu/fdsnws/event/1/query?format=json"
                f"&starttime={t0}&endtime={t1}&lat={lat}&lon={lon}&maxradius=1.5&minmag={max(2.0, mag - 1.5)}&limit=10",
                timeout=12)
        best = None
        for f in r.json().get("features", []):
            fp = f.get("properties") or {}
            try:
                score = abs(float(fp["mag"]) - mag)
            except (KeyError, TypeError, ValueError):
                continue
            if best is None or score < best[0]:
                best = (score, fp)
        if not best or best[0] > 1.0:
            return None
        fp = best[1]
        em, ed = float(fp["mag"]), float(fp.get("depth") or 0)
        agree = best[0] <= 0.3
        verb = "Agrees" if agree else "Differs"
        return {"label": "EMSC cross-check", "tone": "ok" if agree else "warn",
                "value": f"{verb}: M{em:.1f}, {ed:.0f} km (USGS M{mag:.1f}, {float(ev['depth']):.0f} km)",
                "url": f"https://www.seismicportal.eu/eventdetails.html?unid={fp.get('unid', '')}"}

    threads = [threading.Thread(target=run, args=(k, fn), daemon=True)
               for k, fn in (("after", aftershocks), ("gdacs", gdacs), ("emsc", emsc))]
    for t in threads:
        t.start()
    review, fl, prod = usgs_review(), felt(), model_products()
    for t in threads:
        t.join(timeout=30)

    gd = res.get("gdacs") or []
    tsu_tone, tsu_val = ("alert", "Tsunami message issued by NOAA") if ev.get("tsunami") else ("info", "No tsunami message issued")
    for g in gd:
        if g["label"] == "Modelled tsunami":
            tsu_val += f" - modelled up to ~{g['value'].split('~')[1].split(' ')[0]} m"
            tsu_tone = "alert" if ev.get("tsunami") else "warn"
    facts = [review, {"label": "Tsunami", "value": tsu_val, "tone": tsu_tone}, fl]
    facts += [g for g in gd if g["label"] != "Modelled tsunami"]
    facts += [res.get("after"), res.get("emsc"), prod]
    return [f for f in facts if f]


# ── AI narrative ──────────────────────────────────────────────────────────────

def fetch_ai(ev, afs=None, foc=None, bld=None, wea=None):
    """3-sentence analyst narrative via the Anthropic API.
    Requires ANTHROPIC_API_KEY in the environment; returns None otherwise."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        context = []
        if foc:
            context.append(f"Fault: {foc.get('type')} (rake {foc.get('rake')})")
        if bld:
            context.append(f"Stock: {bld.get('dominant')} - {bld.get('vulnerability')} vulnerability")
        if wea:
            context.append(f"Rainfall 3d: {wea.get('precip_3day_mm')} mm, landslide: {wea.get('landslide_risk')}")
        if afs and afs.get("bins"):
            b6 = next((b for b in afs["bins"] if b["mag"] == 6), None)
            if b6:
                context.append(f"M6+ aftershock probability 1 week: {b6['p_1week']}")
        pga_g = round(mmi_to_pga_pctg(ev.get("mmi")) / 100, 2)
        prompt = (
            f"M{ev['mag']:.1f} - {ev['place']}\n"
            f"Depth: {ev['depth']:.0f} km ({ev['depth_note']})\n"
            f"PAGER alert: {ev['pager_alert']}\n"
            f"MMI max: {ev['mmi_label']} ({ev['mmi_desc']})\n"
            f"Est. PGA: {pga_g}g\n"
        )
        if context:
            prompt += "\n".join(context)
        r = post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 320,
                "system": ("You are a senior reinsurance technical analyst. "
                           "Write exactly 3 sentences covering: (1) tectonic context and loss drivers, "
                           "(2) primary risk to insured portfolio, (3) key uncertainties. "
                           "Be precise. No bullet points."),
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=25)
        r.raise_for_status()
        blocks = r.json().get("content", [])
        text = " ".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        return text or None
    except Exception:
        return None
