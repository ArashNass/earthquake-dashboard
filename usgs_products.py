"""
usgs_products.py - Parsers for the USGS event "products" (ShakeMap, PAGER, ground failure,
moment tensor, finite fault, origin, aftershock forecast, summary texts).

Everything here reads published USGS values. Nothing is estimated or guessed: if a product is
missing the parser returns None and the page simply leaves that panel out.

No HTTP happens at import time. Parsers that need a file take a `getter(url, timeout=...)`
callable (fetcher.get) so they can be tested with local fixtures.
"""

import html as _html
import json
import re


# ── small helpers ────────────────────────────────────────────────────────────

def _f(x, nd=None):
    """float(x) or None; optionally rounded."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    if v != v:          # NaN
        return None
    return round(v, nd) if nd is not None else v


def _i(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def product(detail, name):
    """First (preferred) product of a given type, or None."""
    prods = ((detail or {}).get("properties") or {}).get("products") or {}
    lst = prods.get(name) or []
    return lst[0] if lst else None


def _props(detail, name):
    p = product(detail, name)
    return (p or {}).get("properties") or {}


def _read_json(prod, key, getter, timeout=15):
    """Load a JSON file attached to a product (inline bytes or a URL)."""
    c = ((prod or {}).get("contents") or {}).get(key)
    if not c:
        return None
    if "url" not in c and "bytes" in c:
        return json.loads(c["bytes"])
    r = getter(c["url"], timeout=timeout)
    r.raise_for_status()
    return r.json()


def _text(prod, key=""):
    """Inline text of a text product (general-text, impact-text)."""
    c = ((prod or {}).get("contents") or {}).get(key)
    if not c:
        return ""
    return c.get("bytes") or ""


def _strip_html(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def _clip(text, limit):
    """Clip to `limit` characters at a sentence boundary where possible."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    i = max(cut.rfind(". "), cut.rfind(".”"))
    if i > limit * 0.5:
        return cut[:i + 1]
    return cut.rsplit(" ", 1)[0] + "…"


# ── ShakeMap ─────────────────────────────────────────────────────────────────

def shakemap(detail):
    """Peak ground motions and the contour URLs from the ShakeMap product.

    Units are those USGS publishes: MMI (intensity), PGA and spectral acceleration in g,
    PGV in cm/s. These are the maxima over the whole map, not site values.
    """
    p = product(detail, "shakemap")
    if not p:
        return None
    pr = p.get("properties") or {}
    cx = p.get("contents") or {}

    def url(k):
        return (cx.get(k) or {}).get("url", "")

    return {
        "mmi_url": url("download/cont_mmi.json"),
        "pga_url": url("download/cont_pga.json"),
        "peak": {
            "mmi":     _f(pr.get("maxmmi"), 1),
            "pga_g":   _f(pr.get("maxpga"), 3),
            "pgv_cms": _f(pr.get("maxpgv"), 1),
            "sa03_g":  _f(pr.get("maxpsa03"), 3),
            "sa10_g":  _f(pr.get("maxpsa10"), 3),
            "sa30_g":  _f(pr.get("maxpsa30"), 3),
        },
        "version": _i(pr.get("version")),
        "status":  (pr.get("review-status") or "").lower() or None,
        "processed": pr.get("process-timestamp"),
    }


# ── Origin (location quality) ────────────────────────────────────────────────

def origin(detail):
    pr = _props(detail, "origin") or _props(detail, "internal-origin")
    top = (detail or {}).get("properties") or {}
    if not pr and not top:
        return None
    return {
        "depth_type":  pr.get("depth-type"),
        "h_err_km":    _f(pr.get("horizontal-error"), 1),
        "stations":    _i(pr.get("num-stations-used")),
        "gap_deg":     _f(pr.get("azimuthal-gap"), 0),
        "mag_err":     _f(pr.get("magnitude-error"), 2),
        "mag_type":    (pr.get("magnitude-type") or top.get("magType") or "").strip() or None,
        "status":      (top.get("status") or "").lower() or None,    # reviewed / automatic
    }


# ── Focal mechanism ──────────────────────────────────────────────────────────

def classify_rake(rake):
    """(style, lateral sense) from a rake angle in degrees.

    Rake 0 is left-lateral strike-slip, +/-180 right-lateral, +90 reverse, -90 normal
    (Aki and Richards). Oblique styles are the 30-60 degree bands on either side of pure
    reverse or normal slip.
    """
    r = _f(rake)
    if r is None:
        return None, None
    r = ((r + 180.0) % 360.0) - 180.0
    a = abs(r)
    if a <= 30:
        return "Strike-Slip", "Left-lateral"
    if a >= 150:
        return "Strike-Slip", "Right-lateral"
    if 60 <= r <= 120:
        return "Reverse / Thrust", None
    if -120 <= r <= -60:
        return "Normal", None
    if 0 < r < 90:
        return "Oblique Reverse", "Left-lateral"
    if 90 <= r < 180:
        return "Oblique Reverse", "Right-lateral"
    if -90 < r < 0:
        return "Oblique Normal", "Left-lateral"
    return "Oblique Normal", "Right-lateral"


def moment_tensor(detail):
    """Both nodal planes plus the style, from the moment-tensor (or older focal-mechanism) product."""
    for name in ("moment-tensor", "focal-mechanism"):
        pr = _props(detail, name)
        if not pr:
            continue
        planes = []
        for n in (1, 2):
            st, dp, rk = (_f(pr.get(f"nodal-plane-{n}-{k}")) for k in ("strike", "dip", "rake"))
            if st is None or dp is None or rk is None:
                continue
            style, sense = classify_rake(rk)
            planes.append({"strike": round(st), "dip": round(dp), "rake": round(rk), "style": style, "sense": sense})
        if not planes:
            continue
        pc = _f(pr.get("percent-double-couple"))
        return {
            "type":   planes[0]["style"],
            "planes": planes,
            "mw":     _f(pr.get("derived-magnitude"), 1),
            "mw_type": pr.get("derived-magnitude-type"),
            "dc_pct": round(pc * 100) if pc is not None and pc <= 1 else (round(pc) if pc is not None else None),
            "source": pr.get("beachball-source") or pr.get("eventsource"),
        }
    return None


def finite_fault(detail):
    pr = _props(detail, "finite-fault")
    if not pr:
        return None
    length, width = _f(pr.get("model-length")), _f(pr.get("model-width"))
    if length is None:
        return None
    return {
        "length_km": round(length),
        "width_km":  round(width) if width is not None else None,
        "strike":    _f(pr.get("model-strike"), 0),
        "dip":       _f(pr.get("model-dip"), 0),
        "max_slip_m": _f(pr.get("maximum-slip"), 1),
        "mw":        _f(pr.get("derived-magnitude"), 1),
    }


# ── PAGER ────────────────────────────────────────────────────────────────────

def _top_bin(block):
    """Most probable loss bin of a PAGER alert block: (min, max, probability) or None."""
    best = None
    for b in (block or {}).get("bins") or []:
        p = _f(b.get("probability"))
        if p is None:
            continue
        if best is None or p > best["p"]:
            best = {"min": _f(b.get("min")), "max": _f(b.get("max")), "p": round(p, 3)}
    return best


def pager(detail, getter):
    """USGS PAGER impact estimate: fatality and economic alert levels with their published
    probability bins, the PAGER narrative, and population exposed at each intensity."""
    p = product(detail, "losspager")
    if not p:
        return None
    out = {"alert": (_props(detail, "losspager").get("alertlevel") or "").lower() or None}

    try:
        al = _read_json(p, "alerts.json", getter) or {}
        for key in ("fatality", "economic"):
            blk = al.get(key)
            if blk:
                out[key] = {"level": (blk.get("level") or "").lower() or None, "top": _top_bin(blk)}
    except Exception:
        pass

    try:
        cm = _read_json(p, "comments.json", getter) or {}
        out["comments"] = {
            "impact":     [c for c in (cm.get("impact1"), cm.get("impact2")) if c],
            "structures": cm.get("struct_comment") or "",
            "historical": cm.get("historical_comment") or "",
            "secondary":  cm.get("secondary_comment") or "",
        }
    except Exception:
        pass

    try:
        ex = ((_read_json(p, "exposures.json", getter) or {}).get("population_exposure")) or {}
        mmi, pop = ex.get("mmi"), ex.get("aggregated_exposure")
        if mmi and pop and len(mmi) == len(pop):
            out["exposure"] = [{"mmi": int(m), "pop": int(v)} for m, v in zip(mmi, pop)]
    except Exception:
        pass
    return out


# ── Ground failure (landslide and liquefaction) ──────────────────────────────

def ground_failure(detail):
    pr = _props(detail, "ground-failure")
    if not pr:
        return None
    out = {}
    for hz in ("landslide", "liquefaction"):
        alert = (pr.get(f"{hz}-alert") or "").lower() or None
        if not alert:
            continue
        out[hz] = {
            "alert": alert,
            "hazard_km2": _f(pr.get(f"{hz}-hazard-alert-value"), 0),
            "hazard_alert": (pr.get(f"{hz}-hazard-alert-color") or "").lower() or None,
            "pop": _f(pr.get(f"{hz}-population-alert-value"), 0),
            "pop_alert": (pr.get(f"{hz}-population-alert-color") or "").lower() or None,
        }
    return out or None


# ── USGS summary texts ───────────────────────────────────────────────────────

def summary_text(detail):
    """Key points, the tectonic summary and the reported-impact text that USGS publishes.

    Quoted as published (cleaned of markup); the page labels them as USGS text."""
    out = {}
    g = product(detail, "general-text")
    raw = _text(g)
    if raw:
        m = re.search(r"<h2>\s*Key Points\s*(?:\(([^)]*)\))?\s*</h2>(.*?)(?=<h2>|\Z)", raw, re.S | re.I)
        if m:
            bullets = []
            for li in re.findall(r"<li>(.*?)</li>", m.group(2), re.S | re.I):
                t = _strip_html(li)
                if t and not re.search(r"tell us about it|Did You Feel It", t, re.I):
                    bullets.append(t)
            if bullets:
                out["key_points"] = bullets
                out["key_points_updated"] = (m.group(1) or "").replace("updated", "").strip() or None
        m = re.search(r"<h2>\s*Tectonic Summary\s*</h2>(.*?)(?=<h2>|\Z)", raw, re.S | re.I)
        if m:
            paras = [_strip_html(x) for x in re.findall(r"<p>(.*?)</p>", m.group(1), re.S | re.I)]
            paras = [x for x in paras if x]
            if paras:
                out["tectonic"] = _clip(paras[0], 760)
                out["tectonic_truncated"] = len(paras) > 1 or len(paras[0]) > 760
    imp = _strip_html(_text(product(detail, "impact-text")))
    if imp:
        out["impacts"] = _clip(imp, 700)
        out["impacts_truncated"] = len(imp) > 700
    return out or None


# ── Aftershock forecast (USGS Operational Aftershock Forecasting) ────────────

def aftershock_forecast(detail, getter):
    """Probability of at least one aftershock of M5+, M6+, M7+ over 1 day / 1 week / 1 month /
    1 year, plus the expected M3+ count and what has been observed so far.

    USGS publishes forecast.json as a list of time frames, each holding one bin per magnitude
    with `probability` (0-1) and `median` / `p95minimum` / `p95maximum` counts."""
    p = product(detail, "oaf")
    if not p:
        return None
    fc = _read_json(p, "forecast.json", getter) or {}
    frames = {}
    for fr in fc.get("forecast") or []:
        label = (fr.get("label") or "").strip().lower()          # "1 day", "1 week", ...
        frames[label] = {b.get("magnitude"): b for b in fr.get("bins") or [] if b.get("magnitude") is not None}
    if not frames:
        return None

    def prob(label, mag):
        b = (frames.get(label) or {}).get(float(mag))
        return _f((b or {}).get("probability"), 4)

    rows = []
    for mag in (5, 6, 7):
        vals = {k: prob(k, mag) for k in ("1 day", "1 week", "1 month", "1 year")}
        if any(v is not None for v in vals.values()):
            rows.append({"mag": mag, "day": vals["1 day"], "week": vals["1 week"],
                         "month": vals["1 month"], "year": vals["1 year"]})
    if not rows:
        return None

    m3 = (frames.get("1 week") or {}).get(3.0) or {}
    model = (fc.get("model") or {}).get("name")
    return {
        "rows": rows,
        "m3_week": {"median": _i(m3.get("median")), "lo": _i(m3.get("p95minimum")), "hi": _i(m3.get("p95maximum"))}
                   if m3 else None,
        "observed": [{"mag": _f(o.get("magnitude")), "count": _i(o.get("count"))}
                     for o in fc.get("observations") or [] if o.get("magnitude") is not None],
        "issued_ms": _i(fc.get("creationTime")),
        "model": model,
    }
