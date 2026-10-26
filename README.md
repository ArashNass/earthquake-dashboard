# Earthquake Rapid Response Dashboard

**Live dashboard:** https://arashnassirpour.com/earthquake-dashboard/

A self-updating briefing page for the largest earthquakes of the last 90 days. Every figure is a value published by USGS (or another named source), passed through unchanged; the page does not estimate shaking, losses or aftershocks itself.

## What is shown, and where it comes from

| Section | Source |
|---|---|
| Magnitude and type, location, depth and depth type, status, station count, uncertainties | USGS event record (`origin` product) |
| Shaking intensity (MMI), peak ground acceleration (g), peak ground velocity (cm/s), spectral accelerations (0.3 / 1.0 / 3.0 s) and the map contours | USGS ShakeMap product (map-wide maxima, with version and status) |
| Fatality and economic alert levels, most-likely loss bins, population exposed per intensity, USGS impact statements | USGS PAGER product |
| Landslide and liquefaction alert levels, hazard area, people exposed | USGS ground-failure product |
| Fault mechanism, nodal planes, Mw, % double-couple | USGS moment-tensor product |
| Rupture dimensions and maximum slip | USGS finite-fault product; where none exists, the Wells and Coppersmith (1994) average length is shown and labelled as an estimate |
| Aftershock probabilities (M5/6/7+, day to year), expected M3+ count, observed counts | USGS operational aftershock forecast |
| Key points, tectonic setting, reported impacts | USGS event text products |
| Historical context | USGS catalogue (M5.5+, 250 km, 100 years) |
| Media | One link per outlet (BBC News, CNN, Sky News, ABC News): the best matching headline from Google News RSS limited to that outlet, or that outlet's own search page when nothing reliable is found |
| General | Wikipedia (event article only when year, month, day within one and magnitude within 0.5 match; otherwise a search), Wikipedia list of earthquakes of the year, USGS pages, EMSC, GDACS, GEM |
| ReliefWeb | UN OCHA ReliefWeb API: the disaster record for the event (same country, event date within 3 days) and its three latest reports; a ReliefWeb search link when there is no record yet |
| Rainfall | Open-Meteo (context only) |
| Alert strip | USGS, UN GDACS and NASA EONET (fetched by the browser on page load), plus ReliefWeb disasters with status alert, current or ongoing from the last 60 days (fetched at build time, so hourly) |
| Map tiles | Esri |

Failed event-detail requests are reported as unavailable; nothing is invented. A source that fails is omitted. A total build failure exits unsuccessfully so the last good deployment stays live.

## Quick start

```bash
python -m pip install -r requirements.txt
python run.py              # live mode
python run.py --watch      # rebuild every 10 minutes
python run.py --no-ai      # skip optional AI narrative
python run.py --no-open    # do not launch a browser
python run.py --days 7 --limit 3
```

Optional environment variables:

| Variable | Effect |
|---|---|
| `ANTHROPIC_API_KEY` | Enables the optional AI narrative. Without it, that feature is skipped and the rest still builds |
| `RELIEFWEB_APPNAME` | Approved ReliefWeb API appname. Without it, ReliefWeb records and alerts are skipped and a ReliefWeb search link is shown. In production it comes from the repository secret of the same name |

## Architecture

| File | Responsibility |
|---|---|
| `settings.py` | Constants, the MMI scale, PAGER thresholds, timeouts and limits |
| `engine.py` | Event enrichment and the few display calculations |
| `usgs_products.py` | Parsers for the USGS ShakeMap, PAGER, ground-failure, moment-tensor, finite-fault, origin, text and aftershock products |
| `fetcher.py` | External HTTP requests, media and general links |
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

The media-link cache (`media_cache.json`) is kept between runs with `actions/cache`, so Google News is only asked about each event every few hours. `keepalive.yml` pushes an empty commit monthly so GitHub does not disable the schedule after 60 days of inactivity.

Production uses `python run.py --no-open --no-ai`, stages the generated briefing as `dist/index.html`, and deploys it with GitHub Pages. No Netlify configuration or build hook is used.

## Limitations

This dashboard is an automated situational-awareness aid. Source feeds may be delayed, incomplete, revised, or temporarily unavailable. Do not use it as the sole basis for emergency response, life-safety decisions, or engineering assessment.

## Licence

Copyright (C) 2026 Arash Nassirpour.

Licensed under the GNU Affero General Public License v3.0 only (`AGPL-3.0-only`). See [LICENSE](LICENSE).
