# mock_data.py - Demo data for --mock mode and fallback stubs for live failures.

from settings import ALERT_C, BUILDING_STOCK
from fetcher  import get_building_stock, get_country

MOCK_EVENTS = [
    {"id":"us6000t7zp","mag":7.5,"place":"23 km SE of Yumare, Venezuela",
     "time_str":"24 Jun 2026 22:05 UTC","age_str":"2d ago","alert":"RED",
     "tsunami":False,"lat":10.453,"lon":-68.514,"depth":10.0,"has_shakemap":True,
     "url":"https://earthquake.usgs.gov/earthquakes/eventpage/us6000t7zp"},
    {"id":"us6000t7zc","mag":7.2,"place":"24 km ENE of San Felipe, Venezuela",
     "time_str":"24 Jun 2026 22:04 UTC","age_str":"2d ago","alert":"ORANGE",
     "tsunami":False,"lat":10.407,"lon":-68.493,"depth":21.9,"has_shakemap":True,
     "url":"https://earthquake.usgs.gov/earthquakes/eventpage/us6000t7zc"},
    {"id":"us7000srb1","mag":7.8,"place":"24 km SW of Kablalan, Philippines",
     "time_str":"07 Jun 2026 23:37 UTC","age_str":"19d ago","alert":"ORANGE",
     "tsunami":False,"lat":9.0,"lon":126.1,"depth":55.0,"has_shakemap":False,"url":""},
    {"id":"us7000abc1","mag":6.8,"place":"88 km W of Lima, Peru",
     "time_str":"05 Jun 2026 09:12 UTC","age_str":"21d ago","alert":"YELLOW",
     "tsunami":False,"lat":-12.04,"lon":-77.14,"depth":55.0,"has_shakemap":True,"url":""},
    {"id":"us7000abc2","mag":6.4,"place":"12 km NE of Northridge, California",
     "time_str":"04 Jun 2026 06:06 UTC","age_str":"22d ago","alert":"YELLOW",
     "tsunami":False,"lat":34.28,"lon":-118.53,"depth":18.2,"has_shakemap":True,"url":""},
]


def mock_first_event():
    ev = {
        "event_id":"us6000t7zp","mag":7.5,"place":"23 km SE of Yumare, Venezuela",
        "lat":10.453,"lon":-68.514,"depth":10.0,
        "depth_note":"Very shallow - maximum ground motion",
        "t_str":"24 Jun 2026  22:05:12 UTC","t_age_str":"2d ago","t_iso":"2026-06-24",
        "alert_color":"#d32f2f","alert_lbl":"RED","pager_alert":"RED","pager_color":"#d32f2f",
        "mmi":8.7,"mmi_label":"VIII","mmi_desc":"Severe","mmi_effect":"Considerable damage",
        "mmi_color":"#e74c3c","tectonic":"Caribbean Plate - Bocono-Moron-El Pilar Fault System",
        "energy_mt":2.682,"rupture_km":95.5,"tsunami":False,"felt":0,
        "url":"https://earthquake.usgs.gov/earthquakes/eventpage/us6000t7zp",
    }
    sm = {
        "mmi_url": "https://earthquake.usgs.gov/product/shakemap/us6000t7zp/us/1782367573148/download/cont_mmi.json",
        "pga_url": "https://earthquake.usgs.gov/product/shakemap/us6000t7zp/us/1782367573148/download/cont_pga.json",
    }
    afs = {"model":"Reasenberg-Jones","bins":[
        {"mag":5,"p_1day":"94%","p_1week":">99%","p_1month":">99%","n_1week":"~85"},
        {"mag":6,"p_1day":"52%","p_1week":"82%","p_1month":"92%","n_1week":"~9"},
        {"mag":7,"p_1day":"9%","p_1week":"18%","p_1month":"24%","n_1week":"~1"},
    ]}
    foc = {"type":"Strike-Slip","strike":"255","dip":"83","rake":"168"}
    his = [
        {"mag":7.0,"place":"Cariaco, Venezuela","year":1997,"url":"https://earthquake.usgs.gov/earthquakes/eventpage/usp0007xa1"},
        {"mag":6.6,"place":"Caracas, Venezuela","year":1967,"url":""},
        {"mag":6.3,"place":"Yaracuy, Venezuela","year":2009,"url":""},
    ]
    wea = {"temp_c":28.4,"precip_3day_mm":38.5,"landslide_risk":"Moderate"}
    bld = BUILDING_STOCK["Venezuela"]
    news = [
        {"source":"UN GDACS","headline":"RED Alert - Major Earthquake Venezuela M7.5",
         "summary":"3.8 million people in MMI VI+ zone. RED alert issued by UN GDACS.",
         "url":"https://www.gdacs.org"},
        {"source":"GEM Foundation","headline":"Post-Event Assessment: M7.5 Venezuela",
         "summary":"Two large strike-slip earthquakes on the Bocono-Moron-El Pilar fault system. High vulnerability building stock in affected region.",
         "url":"https://www.globalquakemodel.org/post-event-info/us6000t7zp"},
        {"source":"Reuters","headline":"At least 32 dead as twin quakes rock Venezuela",
         "summary":"Buildings collapsed in Caracas. Airport closed. National emergency declared.",
         "url":"https://www.reuters.com/world/americas/earthquakes-shake-venezuela-capital-2026-06-24/"},
        {"source":"USGS PAGER","headline":"RED Alert - Extreme losses expected",
         "summary":"PAGER fatality and economic loss model for M7.5 Venezuela.",
         "url":"https://earthquake.usgs.gov/earthquakes/eventpage/us6000t7zp/pager"},
    ]
    nar = ("A major shallow strike-slip doublet struck the Caribbean-South American plate boundary "
           "in Yaracuy State, with an M7.2 foreshock 39 seconds before the M7.5 mainshock on the "
           "Bocono-Moron-El Pilar fault system at 10 km depth. "
           "Severe shaking (MMI VIII) affected a region of predominantly non-ductile RC and "
           "unreinforced masonry, amplifying structural damage significantly above what magnitude "
           "alone would suggest, with direct insured loss potential in the USD 500M-2B range. "
           "Key uncertainties include aftershock sequence duration (18% M7+ probability in one week), "
           "business interruption from port and airport closures, and political risk affecting claims settlement.")
    return dict(ev=ev, sm=sm, aftershock=afs, focal=foc, historical=his,
                weather=wea, building=bld, news=news, narrative=nar)


def mock_stub(e):
    """Stub data for non-primary mock events (also the live-mode fallback)."""
    eid   = e["id"]
    mag   = e["mag"]
    place = e["place"]
    alert = e.get("alert") or "N/A"
    ac    = ALERT_C.get(alert, ALERT_C[""])
    dn    = ("Very shallow" if e["depth"] <= 30 else
             "Shallow"      if e["depth"] <= 70 else "Intermediate")
    country = get_country(place)

    news = []
    if alert in ("RED", "ORANGE", "YELLOW"):
        gdacs_desc = {
            "RED":    f"RED alert. M{mag} causes severe shaking. Large exposed population.",
            "ORANGE": f"ORANGE alert. M{mag} - significant shaking in populated areas.",
            "YELLOW": f"YELLOW alert. M{mag} - moderate shaking. Limited losses expected.",
        }[alert]
        news.append({"source":"UN GDACS",
                     "headline":f"{alert} Alert - M{mag} {country}",
                     "summary":gdacs_desc,
                     "url":f"https://www.gdacs.org/Earthquakes/Eventdetails.aspx?EQEventID={eid}"})
    if alert in ("RED", "ORANGE"):
        news.append({"source":"USGS PAGER",
                     "headline":f"{alert} Alert - {'Extreme' if alert == 'RED' else 'Significant'} losses expected",
                     "summary":f"PAGER loss model for M{mag} {place}.",
                     "url":f"https://earthquake.usgs.gov/earthquakes/eventpage/{eid}/pager"})
    if alert == "RED":
        news.append({"source":"GEM Foundation",
                     "headline":f"Post-Event Assessment: M{mag} {country} (pending 24h)",
                     "summary":"GEM Foundation assessment expected within 24 hours for this RED alert event.",
                     "url":f"https://www.globalquakemodel.org/post-event-info/{eid}"})
    # Region-specific sources
    if "Philippines" in place:
        news.append({"source":"PHIVOLCS",
                     "headline":f"PHIVOLCS Bulletin - M{mag} {place}",
                     "summary":"Philippine seismological monitoring active. Aftershocks being tracked.",
                     "url":"https://www.phivolcs.dost.gov.ph"})
    if any(c in place for c in ("Peru", "Chile", "Ecuador", "Colombia")):
        news.append({"source":"IGP Peru",
                     "headline":f"Regional bulletin - M{mag} {place}",
                     "summary":"Regional seismological monitoring active.",
                     "url":"https://ultimosismo.igp.gob.pe"})
    if "California" in place or ("United States" in place and "Alaska" not in place):
        news.append({"source":"USGS",
                     "headline":f"ShakeAlert activated - M{mag} {place}",
                     "summary":"USGS early warning system and ShakeMap being computed.",
                     "url":f"https://earthquake.usgs.gov/earthquakes/eventpage/{eid}"})
    news.append({"source":"USGS NEIC",
                 "headline":f"Event Page: M{mag} - {place}",
                 "summary":"Official USGS parameters, ShakeMap, DYFI reports and aftershock monitoring.",
                 "url":f"https://earthquake.usgs.gov/earthquakes/eventpage/{eid}"})

    return dict(
        ev={
            "event_id":   eid, "mag": mag, "place": place,
            "lat": e["lat"], "lon": e["lon"], "depth": e["depth"],
            "depth_note": dn, "t_str": e["time_str"], "t_age_str": e["age_str"],
            "t_iso": "", "alert_color": ac, "alert_lbl": alert,
            "pager_alert": alert, "pager_color": ac,
            "mmi": 0, "mmi_label": "--", "mmi_desc": "--",
            "mmi_effect": "", "mmi_color": "#ccc",
            "tectonic": "", "energy_mt": 0, "rupture_km": 0,
            "tsunami": e.get("tsunami", False), "felt": 0,
            "url": e.get("url", ""),
        },
        sm={"mmi_url": "", "pga_url": ""},
        aftershock=None, focal=None, historical=[],
        weather=None, building=get_building_stock(place),
        news=news, narrative=None,
    )
