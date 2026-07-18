"""
run.py - Entry point. Run this.
  python run.py            Live mode
  python run.py --mock     Demo mode (no internet needed)
  python run.py --no-ai    Skip AI narrative (also skipped when ANTHROPIC_API_KEY is unset)
  python run.py --watch    Auto-refresh every 10 minutes (browser opens once)
  python run.py --no-open  Build the file without opening a browser
  python run.py --days 7 --limit 3   Custom query window / event count
"""
import sys
import time
import argparse
import threading
import webbrowser
from pathlib import Path
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from settings   import OUTPUT_FILE, REFRESH_MINUTES, QUERY_DAYS, QUERY_LIMIT, ALERT_C
from fetcher    import (fetch_top_events, fetch_detail, enrich,
                        extract_shakemap, extract_aftershock, extract_focal,
                        fetch_historical, fetch_weather, fetch_news, fetch_ai,
                        get_building_stock)
from mock_data  import MOCK_EVENTS, mock_first_event, mock_stub
from dashboard  import build


def load_one(stub, no_ai=False):
    """Fetch all data for one live event. Falls back to a stub on failure."""
    try:
        detail = fetch_detail(stub["id"])
        ev     = enrich(detail)
        # USGS can return the event under a different preferred catalog id than
        # the one used in the top-events list. The sidebar is built from the
        # list, so pin the id to the list's id or sidebar clicks won't match.
        ev["event_id"] = stub["id"]
        sm     = extract_shakemap(detail)

        # Run the slower fetches in parallel.
        results = {}

        def run_fetch(key, fn):
            try:
                results[key] = fn()
            except Exception as ex:
                print(f"    [WARN] {stub['id']} {key}: {ex}")
                results[key] = None

        threads = [
            threading.Thread(target=run_fetch, args=("afs", lambda: extract_aftershock(detail)), daemon=True),
            threading.Thread(target=run_fetch, args=("foc", lambda: extract_focal(detail)), daemon=True),
            threading.Thread(target=run_fetch, args=("his", lambda: fetch_historical(
                ev["lat"], ev["lon"], ev["event_id"], before_iso=ev.get("t_iso"))), daemon=True),
            threading.Thread(target=run_fetch, args=("wea", lambda: fetch_weather(ev["lat"], ev["lon"])), daemon=True),
            threading.Thread(target=run_fetch, args=("nws", lambda: fetch_news(ev)), daemon=True),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        afs = results.get("afs")
        foc = results.get("foc")
        wea = results.get("wea")
        bld = get_building_stock(ev["place"])
        nar = None if no_ai else fetch_ai(ev, afs, foc, bld, wea)

        return dict(ev=ev, sm=sm,
                    aftershock=afs, focal=foc,
                    historical=results.get("his") or [],
                    weather=wea, building=bld,
                    news=results.get("nws") or [],
                    narrative=nar)
    except Exception as ex:
        print(f"    [WARN] {stub['id']}: {ex} - detail feed failed, marking unavailable (no invented data)")
        return {
            "ev": {
                "event_id": stub["id"], "mag": stub["mag"], "place": stub["place"],
                "lat": stub["lat"], "lon": stub["lon"], "depth": stub["depth"],
                "depth_note": "", "t_str": stub.get("time_str", ""), "t_age_str": stub.get("age_str", ""),
                "alert_color": ALERT_C.get(stub.get("alert") or "", ALERT_C[""]),
                "alert_lbl": stub.get("alert") or "N/A", "pager_alert": "N/A", "pager_color": ALERT_C[""],
                "mmi": 0, "mmi_label": "--", "mmi_desc": "--", "mmi_effect": "",
                "mmi_color": "#ccc", "tectonic": "", "energy_mt": 0, "rupture_km": 0,
                "tsunami": stub.get("tsunami", False), "url": stub.get("url", ""),
            },
            "sm": {"mmi_url": "", "pga_url": ""},
            "aftershock": None, "focal": None, "historical": [],
            "weather": None, "building": None, "news": [], "narrative": None,
            "data_unavailable": True, "error_detail": str(ex),
        }


def run(args, open_browser=True):
    print(f"\n[{datetime.now():%H:%M:%S}] Earthquake Rapid Response Dashboard")

    if args.mock:
        print("  [MOCK] Demo mode - Venezuela M7.5")
        top_events = MOCK_EVENTS
        all_data   = [mock_first_event()] + [mock_stub(e) for e in MOCK_EVENTS[1:]]
    else:
        print(f"  Fetching top {args.limit} earthquakes from USGS (last {args.days} days)...")
        try:
            top_events = fetch_top_events(days=args.days, limit=args.limit)
        except Exception as ex:
            print(f"  [ERROR] USGS unreachable: {ex}")
            print("  Try: python run.py --mock")
            return False

        if not top_events:
            print("  [ERROR] No events returned.")
            return False

        print(f"  Found {len(top_events)}. Largest: M{top_events[0]['mag']} {top_events[0]['place']}")

        all_data = [None] * len(top_events)

        def load_slot(i, stub):
            print(f"  [{i + 1}/{len(top_events)}] M{stub['mag']} {stub['place'][:50]}...")
            all_data[i] = load_one(stub, args.no_ai)

        ev_threads = [threading.Thread(target=load_slot, args=(i, e), daemon=True)
                      for i, e in enumerate(top_events)]
        for t in ev_threads:
            t.start()
        for t in ev_threads:
            t.join()

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print("  Building dashboard...")
    html = build(top_events, all_data, now_str)
    out  = HERE / OUTPUT_FILE
    out.write_text(html, encoding="utf-8")
    print(f"  Saved: {out.name}  ({out.stat().st_size // 1024} KB)")

    if open_browser and not args.no_open:
        try:
            webbrowser.open(out.as_uri())
        except Exception:
            print(f"  Open manually: {out.as_uri()}")
    print("  Done.\n")
    return True


def main():
    p = argparse.ArgumentParser(description="Earthquake Rapid Response Dashboard")
    p.add_argument("--mock",    action="store_true", help="Demo mode, no internet needed")
    p.add_argument("--no-ai",   action="store_true", help="Skip AI narrative")
    p.add_argument("--no-open", action="store_true", help="Don't open the browser")
    p.add_argument("--watch",   action="store_true", help=f"Auto-refresh every {REFRESH_MINUTES} min")
    p.add_argument("--days",    type=int, default=QUERY_DAYS,  help="Look-back window in days")
    p.add_argument("--limit",   type=int, default=QUERY_LIMIT, help="Number of events")
    args = p.parse_args()

    if args.watch:
        first = True
        while True:
            try:
                # Only open the browser on the first cycle; the file is
                # rewritten in place afterwards - just refresh the tab.
                run(args, open_browser=first)
                first = False
                print(f"  Next refresh in {REFRESH_MINUTES} min (Ctrl+C to stop)")
                time.sleep(REFRESH_MINUTES * 60)
            except KeyboardInterrupt:
                print("\nStopped.")
                sys.exit(0)
    else:
        ok = run(args)
        if not ok:
            print("  [FATAL] Build failed - not writing output. Previous deployed version, if any, stays live.")
            sys.exit(1)


if __name__ == "__main__":
    main()
