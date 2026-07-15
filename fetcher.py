# fetcher.py - All HTTP data fetching. Enrichment lives in engine.py.

import os
import re
import threading
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta, date

import requests
from requests.adapters import HTTPAdapter, Retry

from settings import (BUILDING_STOCK, US_STATES, REGION_WORDS,
                      NEWS_SOURCE_ORDER, SSL, HTTP_TIMEOUT, HTTP_RETRIES,
                      USER_AGENT, QUERY_DAYS, QUERY_LIMIT, QUERY_MIN_MAG)
from engine import enrich, mmi_to_pga_pctg  # re-exported for run.py

__all__ = ["fetch_top_events", "fetch_detail", "enrich", "extract_shakemap",
           "extract_aftershock", "extract_focal", "fetch_historical",
           "fetch_weather", "fetch_news", "fetch_ai",
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
        })
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

# ── Intelligence (5 sources, parallel) ───────────────────────────────────────

def fetch_news(ev):
    """Fetch intelligence from 5 parallel sources. No API keys needed."""
    news = []
    lock = threading.Lock()

    eid      = ev["event_id"]
    mag      = ev["mag"]
    place    = ev["place"]
    alert    = ev.get("pager_alert", "")
    country  = get_country(place)
    year     = (ev.get("t_iso") or "")[:4] or str(datetime.now(timezone.utc).year)
    event_dt = ev.get("t_iso") or date.today().isoformat()

    def add(item):
        if item and isinstance(item, dict) and item.get("headline"):
            with lock:
                news.append(item)

    # 1. GEM Foundation
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

    # 2. ReliefWeb API
    def _reliefweb():
        try:
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
            r = post("https://api.reliefweb.int/v2/reports?appname=eq-dashboard",
                     json=payload, timeout=12)
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

    # 3. Wikipedia
    def _wikipedia():
        try:
            title = f"{year}_{country}_earthquakes".replace(" ", "_")
            r = get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}", timeout=10)
            if r.status_code != 200:
                r2 = get("https://en.wikipedia.org/w/api.php",
                         params={"action": "opensearch", "search": f"{year} {country} earthquake",
                                 "limit": 1, "format": "json"},
                         timeout=8)
                if r2.status_code != 200 or not r2.json()[1]:
                    return
                title = r2.json()[1][0].replace(" ", "_")
                r = get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}", timeout=8)
                if r.status_code != 200:
                    return
            d       = r.json()
            extract = d.get("extract", "")
            if len(extract) > 60:
                sentences = extract.split(". ")
                summary = ". ".join(sentences[:2]).strip()
                if not summary.endswith("."):
                    summary += "."
                add({"source": "Wikipedia",
                     "headline": d.get("title", ""),
                     "summary": summary[:300],
                     "url": d.get("content_urls", {}).get("desktop", {}).get("page", "")})
        except Exception:
            pass

    # 4. EMSC
    def _emsc():
        try:
            r = get(f"https://www.seismicportal.eu/fdsnws/event/1/query"
                    f"?format=json&lat={ev['lat']}&lon={ev['lon']}"
                    f"&maxradius=2&minmag={max(5.0, float(mag) - 1.0)}&limit=3",
                    timeout=10)
            if r.status_code != 200:
                return
            feats = r.json().get("features", [])
            if feats:
                p = feats[0]["properties"]
                add({"source": "EMSC",
                     "headline": f"Independent parameters: M{p.get('mag')} {p.get('flynn_region', '')}",
                     "summary": f"Depth {p.get('depth')} km. Agency: {p.get('auth', 'EMSC')}. Independent European verification.",
                     "url": f"https://www.seismicportal.eu/eventdetails.html?unid={p.get('unid', '')}"})
        except Exception:
            pass

    # 5. GDACS + PAGER
    def _gdacs():
        try:
            r    = get("https://www.gdacs.org/xml/rss_eq.xml", timeout=10)
            root = ET.fromstring(r.content)
            clow = country.lower()
            for item in root.iter("item"):
                title = item.findtext("title", "")
                link  = item.findtext("link", "")
                desc  = item.findtext("description", "")
                if clow and (clow in title.lower() or clow in desc.lower()):
                    add({"source": "UN GDACS",
                         "headline": title[:120],
                         "summary": re.sub(r'<[^>]+>', "", desc)[:200].strip(),
                         "url": link})
                    break
        except Exception:
            pass
        if alert in ("RED", "ORANGE"):
            add({"source": "USGS PAGER",
                 "headline": f"{alert} Alert - {'Extreme' if alert == 'RED' else 'Significant'} losses expected",
                 "summary": f"PAGER fatality and economic loss model for M{mag} {place}.",
                 "url": f"https://earthquake.usgs.gov/earthquakes/eventpage/{eid}/pager"})

    threads = [threading.Thread(target=fn, daemon=True)
               for fn in (_gem, _reliefweb, _wikipedia, _emsc, _gdacs)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    news.sort(key=lambda x: next(
        (i for i, s in enumerate(NEWS_SOURCE_ORDER) if s == x["source"]), 99))
    return news[:6]

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
