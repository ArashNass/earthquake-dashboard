# Earthquake Rapid Response Dashboard

**Live dashboard:** https://arashnassirpour.com/earthquake-dashboard/

A self-updating briefing page for the largest earthquakes of the last 30 days. It combines ShakeMap ground-motion layers, aftershock forecasts, fault mechanisms, historical seismicity, weather-driven landslide context, building-stock vulnerability, disaster alerts, and multi-source news.

## Data sources

The build retrieves current information from USGS, GDACS, ReliefWeb, EMSC, Open-Meteo, and selected reference sources. External data remains attributed in the generated dashboard.

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

The optional AI narrative uses `ANTHROPIC_API_KEY`. Without the variable, that feature is skipped and the rest of the dashboard still builds.

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

TLS verification is enabled by default. Dynamic text is escaped and embedded JSON is protected against premature script termination. The generated report remains usable without further network access; map tiles and third-party browser assets degrade gracefully if unavailable.

## Deployment

`.github/workflows/refresh.yml` builds and deploys the dashboard to GitHub Pages:

- Hourly on the hour, UTC.
- On every push to `main`.
- Manually through `workflow_dispatch`.

Production uses `python run.py --no-open --no-ai`, stages the generated briefing as `dist/index.html`, and deploys it with GitHub Pages. No Netlify configuration or build hook is used.

## Limitations

This dashboard is an automated situational-awareness aid. Source feeds may be delayed, incomplete, revised, or temporarily unavailable. Do not use it as the sole basis for emergency response, life-safety decisions, or engineering assessment.

## Licence

Copyright (C) 2026 Arash Nassirpour.

Licensed under the GNU Affero General Public License v3.0 only (`AGPL-3.0-only`). See [LICENSE](LICENSE).
