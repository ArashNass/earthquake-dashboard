"""
engine.py - Event enrichment and the few seismology calculations the page still makes.
No network access in this module.

Everything else on the page (peak ground motions, PAGER, ground failure, mechanism, aftershock
forecast, tectonic summary) is read straight from the USGS products in usgs_products.py, never
estimated here.
"""

from datetime import datetime, timezone

from settings import ALERT_C, MMI_SCALE


def depth_class(depth_km):
    """Standard depth classes for hypocentres."""
    if depth_km > 300:
        return "Deep (over 300 km)"
    if depth_km > 70:
        return "Intermediate (70 to 300 km)"
    return "Shallow (under 70 km)"


def energy_megatons(mag):
    """Radiated seismic energy, log10 E[J] = 1.5 M + 4.8 (Gutenberg-Richter), as megatons of TNT
    (1 Mt = 4.184e15 J). A comparison figure, not the energy released by the whole process."""
    if not mag:
        return 0.0
    return round(10 ** (1.5 * mag + 4.8) / 4.184e15, 3)


def rupture_length_km(mag):
    """Expected subsurface rupture length, Wells and Coppersmith (1994), all slip types:
    log10 L[km] = -2.44 + 0.59 M. An empirical average; individual events scatter widely."""
    if not mag:
        return 0.0
    return round(10 ** (-2.44 + 0.59 * mag), 1)


def mmi_info(mmi):
    """Roman numeral, perceived shaking, potential damage and colour for an intensity value."""
    if not mmi or mmi <= 0:
        return None
    n = max(1, min(10, int(round(mmi))))
    roman, shaking, damage, color, pga, pgv = MMI_SCALE[n]
    return {"roman": roman, "shaking": shaking, "damage": damage, "color": color, "pga_ref": pga, "pgv_ref": pgv}


def enrich(detail):
    """Turn a USGS GeoJSON detail feature into the flat event dict used everywhere.

    Defensive against missing/null fields: mag, mmi, alert and time may all be None on fresh events.
    """
    p = detail.get("properties") or {}
    c = (detail.get("geometry") or {}).get("coordinates") or [0, 0, 0]
    lon, lat, depth = float(c[0]), float(c[1]), float(c[2])

    mag = float(p.get("mag") or 0)
    t_ms = int(p.get("time") or 0)
    t = datetime.fromtimestamp(t_ms / 1000, tz=timezone.utc)

    mmi = round(float(p.get("mmi") or 0), 1)
    mi = mmi_info(mmi) or {}

    alert = (p.get("alert") or "").upper()
    ac = ALERT_C.get(alert or "N/A", ALERT_C[""])

    # The full feed id ("us6000t7zc") must be used, not properties.code
    # ("6000t7zc"), because the sidebar looks events up by feed id.
    event_id = (detail.get("id") or p.get("code") or "").strip(",")

    return {
        "event_id":    event_id,
        "mag":         mag,
        "mag_type":    (p.get("magType") or "").strip(),
        "place":       p.get("place") or "Unknown location",
        "lat":         lat,
        "lon":         lon,
        "depth":       depth,
        "depth_note":  depth_class(depth),
        "t_str":       t.strftime("%d %b %Y %H:%M:%S UTC"),
        "t_ms":        t_ms,
        "t_iso":       t.strftime("%Y-%m-%d"),
        "t_utc":       t.strftime("%Y-%m-%dT%H:%M:%S"),
        "alert_color": ac,
        "pager_alert": alert,                     # overall PAGER level, "" when not yet issued
        "status":      (p.get("status") or "").lower(),   # reviewed / automatic
        "mmi":         mmi,
        "mmi_roman":   mi.get("roman", ""),
        "mmi_shaking": mi.get("shaking", ""),
        "mmi_damage":  mi.get("damage", ""),
        "mmi_color":   mi.get("color", "#ccc"),
        "felt":        int(p.get("felt") or 0),
        "cdi":         round(float(p["cdi"]), 1) if p.get("cdi") else None,
        "tsunami":     bool(p.get("tsunami")),
        "energy_mt":   energy_megatons(mag),
        "rupture_km":  rupture_length_km(mag),
        "url":         p.get("url") or f"https://earthquake.usgs.gov/earthquakes/eventpage/{event_id}",
    }
