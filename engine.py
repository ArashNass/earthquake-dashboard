"""
engine.py - Event enrichment and seismology calculations.
Change calculations or tectonic zones here only. No network access in this module.
"""

from datetime import datetime, timezone

from settings import ALERT_C, MMI_SCALE

# Ordered most-specific first; the first matching box wins.
TECTONIC_ZONES = [
    (lambda la, lo: -75 <= lo <= -63 and    8 <= la <= 12, "Caribbean Plate - Bocono-Moron-El Pilar Fault System"),
    (lambda la, lo: -120 <= lo <= -114 and 32 <= la <= 42, "San Andreas Fault system"),
    (lambda la, lo:  130 <= lo <= 150 and  30 <= la <= 46, "Japan subduction zone (Pacific Plate)"),
    (lambda la, lo:  -75 <= lo <= -65 and -45 <= la <= 10, "South American subduction zone (Nazca Plate)"),
    (lambda la, lo: -130 <= lo <= -110 and 38 <= la <= 55, "Cascadia subduction zone"),
    (lambda la, lo:   95 <= lo <= 140 and -10 <= la <= 20, "Sunda/Java subduction zone"),
    (lambda la, lo:   24 <= lo <=  44 and  35 <= la <= 42, "North Anatolian Fault region"),
    (lambda la, lo:  -90 <= lo <= -60 and  10 <= la <= 22, "Caribbean subduction zone"),
    (lambda la, lo:   65 <= lo <=  85 and  25 <= la <= 40, "Himalayan collision zone"),
]


def tectonic_zone(lat, lon):
    """Coarse tectonic classification from bounding boxes."""
    return next((label for fn, label in TECTONIC_ZONES if fn(lat, lon)),
                "Intraplate / undefined region")


def depth_note(depth_km):
    if depth_km > 300:
        return "Deep focus - reduced surface damage"
    if depth_km > 70:
        return "Intermediate depth"
    if depth_km > 30:
        return "Shallow - elevated damage potential"
    return "Very shallow - maximum ground motion"


def energy_megatons(mag):
    """Radiated seismic energy (Gutenberg-Richter), expressed in megatons of TNT."""
    if not mag:
        return 0.0
    return round(10 ** (1.5 * mag + 4.8) / 4.184e15, 3)


def rupture_length_km(mag):
    """Approximate rupture length (Wells and Coppersmith style scaling)."""
    if not mag:
        return 0.0
    return round(10 ** (0.5 * mag - 1.77), 1)


def mmi_to_pga_pctg(mmi):
    """Approximate peak ground acceleration in %g from MMI (Worden et al. inversion)."""
    if not mmi or mmi <= 0:
        return 0
    return min(300, round(10 ** ((mmi - 1.78) / 2.5)))


def enrich(detail):
    """Turn a USGS GeoJSON detail feature into the flat event dict used everywhere.

    Defensive against missing/null fields: mag, mmi, alert and time may all be None
    on fresh events.
    """
    p = detail.get("properties") or {}
    c = (detail.get("geometry") or {}).get("coordinates") or [0, 0, 0]
    lon, lat, depth = float(c[0]), float(c[1]), float(c[2])

    mag   = float(p.get("mag") or 0)
    t     = datetime.fromtimestamp((p.get("time") or 0) / 1000, tz=timezone.utc)
    age_h = (datetime.now(timezone.utc) - t).total_seconds() / 3600

    mmi = float(p.get("mmi") or 0)
    ms  = MMI_SCALE.get(int(round(mmi)), ("--", "--", "--", "#ccc"))

    alert = (p.get("alert") or "").upper()
    ac    = ALERT_C.get(alert or "N/A", ALERT_C[""])

    # The full feed id ("us6000t7zc") must be used, not properties.code
    # ("6000t7zc"), because the sidebar looks events up by feed id.
    event_id = (detail.get("id") or p.get("code") or "").strip(",")

    return {
        "event_id":    event_id,
        "mag":         mag,
        "place":       p.get("place") or "Unknown location",
        "lat":         lat,
        "lon":         lon,
        "depth":       depth,
        "depth_note":  depth_note(depth),
        "t_str":       t.strftime("%d %b %Y  %H:%M:%S UTC"),
        "t_age_str":   (f"{int(age_h)}h {int((age_h % 1) * 60)}m ago" if 0 <= age_h < 48
                        else f"{int(age_h / 24)}d ago" if age_h >= 48
                        else t.strftime("%d %b %Y")),
        "t_iso":       t.strftime("%Y-%m-%d"),
        "alert_color": ac,
        "alert_lbl":   alert or "N/A",
        "pager_alert": alert or "N/A",
        "pager_color": ac,
        "mmi":         mmi,
        "mmi_label":   ms[0],
        "mmi_desc":    ms[1],
        "mmi_effect":  ms[2],
        "mmi_color":   ms[3],
        "felt":        int(p.get("felt") or 0),
        "tsunami":     bool(p.get("tsunami")),
        "tectonic":    tectonic_zone(lat, lon),
        "energy_mt":   energy_megatons(mag),
        "rupture_km":  rupture_length_km(mag),
        "url":         p.get("url") or f"https://earthquake.usgs.gov/earthquakes/eventpage/{event_id}",
    }
