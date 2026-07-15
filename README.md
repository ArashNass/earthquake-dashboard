# Earthquake Rapid Response Dashboard

**Live:** https://arashnassirpour.com/dashboard/

A self-updating briefing page for the largest earthquakes of the last 30 days.
For each event it shows ShakeMap ground-motion layers on an interactive map,
aftershock probability forecasts, fault mechanism, historical seismicity,
weather-driven landslide risk, building stock vulnerability, and multi-source
news - all fetched live from USGS, GDACS, ReliefWeb, EMSC and Open-Meteo.
The site rebuilds itself every 6 hours via a scheduled GitHub Action that
publishes to GitHub Pages; any commit to `main` also deploys automatically.

## Quick start

```
pip install requests
python run.py              # live mode
python run.py --mock       # demo mode, no internet needed
python run.py --watch      # rebuild every 10 minutes (browser opens once)
python run.py --no-ai      # skip AI narrative
python run.py --no-open    # build without opening a browser
python run.py --days 7 --limit 3
```

The AI narrative requires an `ANTHROPIC_API_KEY` environment variable; without
it the narrative is skipped silently and everything else still works.

## File responsibilities (edit only the file that owns the concern)

| File              | Owns                                                              |
|-------------------|-------------------------------------------------------------------|
| `settings.py`     | All constants: colours, scales, building stock, timeouts, limits  |
| `engine.py`       | Enrichment and seismology maths (energy, rupture, tectonic zones) |
| `fetcher.py`      | All HTTP: USGS, ReliefWeb, Wikipedia, EMSC, GDACS, Open-Meteo, AI |
| `mock_data.py`    | Demo data and the fallback stub used when a live fetch fails      |
| `dashboard.py`    | HTML shell, CSS, sidebar, JSON serialisation and injection        |
| `dashboard_js.js` | All client-side rendering and the Leaflet map (single source)     |
| `run.py`          | CLI entry point and orchestration                                 |

`dashboard.py` reads `dashboard_js.js` at build time and injects the data via
the `__ALL_DATA__` / `__FIRST_ID__` / `__MMI_COLORS__` / `__ALERT_C__` /
`__PAGER_DESC__` placeholders, so the JS file must sit next to it.

## Notes

- TLS verification is on by default (`SSL = True` in `settings.py`). Only set
  it to `False` behind an intercepting corporate proxy.
- All dynamic strings (place names, news headlines) are HTML-escaped both
  server-side and client-side; embedded JSON is `</script>`-safe.
- The map degrades gracefully when the Leaflet CDN is unreachable; the report
  itself never depends on the network once the HTML is built.

## Live deployment on Netlify (auto-refresh a few times a day)

Netlify hosts static files only, so the "live" mechanism is scheduled rebuilds:
a timer triggers Netlify, Netlify runs `run.py` on its build machine and
publishes the fresh HTML. Setup once, then it runs itself:

1. Push this folder to a GitHub repository.
2. In Netlify: Add new site -> Import an existing project -> pick the repo.
   Netlify reads `netlify.toml` automatically; no settings needed.
3. In Netlify: Site configuration -> Build & deploy -> Build hooks ->
   Add build hook. Copy the URL.
4. In GitHub: repo Settings -> Secrets and variables -> Actions ->
   New repository secret named `NETLIFY_BUILD_HOOK`, paste the URL.

Done. The workflow in `.github/workflows/refresh.yml` now rebuilds the site
every 6 hours (edit the cron line to change frequency). The timestamp in the
page's top-right corner shows when it was last generated.

Optional: to enable the AI narrative, remove `--no-ai` from the build command
in `netlify.toml` and add `ANTHROPIC_API_KEY` as a Netlify environment
variable (Site configuration -> Environment variables). Never commit the key.

Note: a free Netlify site is public to anyone with the URL. Password
protection requires a paid Netlify plan - consider whether that matters given
the "Internal Use Only" label before sharing the link.
