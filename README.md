# Earthquake Rapid Response Dashboard

**Live dashboard:** https://arashnassirpour.com/earthquake-dashboard/

A self-updating briefing page for the largest earthquakes of the last 90 days. It combines ShakeMap ground-motion layers, aftershock forecasts, fault mechanisms, historical seismicity, weather-driven landslide context, building-stock vulnerability, a global disaster-alert ticker, and an event-specific intelligence panel (verified facts plus matching reports and headlines).

## Data sources

| Source | Used for |
|---|---|
| USGS | Event list, event record (review status, tsunami flag, "Did You Feel It" reports), ShakeMap contours, aftershock forecast and counts, focal mechanism, historical seismicity |
| UN GDACS (JSON API) | Alert level, population exposed, modelled tsunami height, matched to the USGS event by place, time and magnitude |
| EMSC | Independent cross-check of magnitude and depth (shown as "Agrees" or "Differs") |
| GEM Foundation | Post-event assessment, where one exists |
| Wikipedia | Event article, shown only if its year, month, day (within one) and magnitude (within 0.5) match the event |
| GDELT | Up to three recent news headlines per event; cached per event (6 h, or 30 min after a failed call) because GDELT allows one request per 5 s |
| UN ReliefWeb | Humanitarian reports. Needs an approved app name: set `RELIEFWEB_APPNAME`; without it the source yields nothing |
| NASA EONET + USGS | Global disaster-alert ticker |
| Open-Meteo | Recent rainfall for landslide context |
| Esri | Map tiles (World Street Map and World Imagery) |

External data remains attributed in the generated dashboard. Items that cannot be tied to the event are dropped rather than shown, and a source that fails is simply omitted.

Failed event-detail requests are reported honestly as unavailable. The production build does not invent replacement news, narratives, or measurements; verified USGS summary fields remain visible where available. A total build failure exits unsuccessfully so the last good deployment stays live.

## Quick start

```bash
python -m pip install -r requirements.txt
python run.py              # live mode
python run.py --mock       # deterministic demo mode
python run.py --watch      # rebuild every 10 minutes
python run.py --no-ai      # skip optional AI narrative
python run.py --no-open    # do not launch a browser
python run.py --days 7 --limit 3
```

Optional environment variables:

| Variable | Effect |
|---|---|
| `ANTHROPIC_API_KEY` | Enables the AI narrative. Without it, that feature is skipped and the rest still builds |
| `RELIEFWEB_APPNAME` | Approved ReliefWeb app name, enabling humanitarian reports |

## Architecture

| File | Responsibility |
|---|---|
| `settings.py` | Constants, scales, timeouts, building stock, and limits |
| `engine.py` | Seismology calculations and enrichment |
| `fetcher.py` | External HTTP requests and source handling |
| `mock_data.py` | Demo data and deterministic fallback fixtures |
| `dashboard.py` | HTML shell, CSS, serialisation, and data injection |
| `dashboard_js.js` | Client-side rendering and Leaflet map |

| `run.py` | CLI and build orchestration |

The page includes a Standard / Sentinel theme switch. The optional Sentinel mission-control theme is loaded on demand from `/sentinel/` in the main site repository (`arashnass.github.io`); locally, or anywhere that path does not exist, the switch simply has no effect.

TLS verification is enabled by default. Dynamic text is escaped and embedded JSON is protected against premature script termination. The generated report remains usable without further network access; map tiles and third-party browser assets degrade gracefully if unavailable.

## Deployment

`.github/workflows/refresh.yml` builds and deploys the dashboard to GitHub Pages:

- Hourly on the hour, UTC.
- On every push to `main`.
- Manually through `workflow_dispatch`.

The headline cache (`headlines_cache.json`) is kept between runs with `actions/cache`, so GDELT is only asked about each event every few hours. `keepalive.yml` pushes an empty commit monthly so GitHub does not disable the schedule after 60 days of inactivity.

Production uses `python run.py --no-open --no-ai`, stages the generated briefing as `dist/index.html`, and deploys it with GitHub Pages. No Netlify configuration or build hook is used.

## Limitations

This dashboard is an automated situational-awareness aid. Source feeds may be delayed, incomplete, revised, or temporarily unavailable. Do not use it as the sole basis for emergency response, life-safety decisions, or engineering assessment.

## Licence

Copyright (C) 2026 Arash Nassirpour.

Licensed under the GNU Affero General Public License v3.0 only (`AGPL-3.0-only`). See [LICENSE](LICENSE).
