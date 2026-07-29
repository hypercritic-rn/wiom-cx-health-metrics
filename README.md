# Wiom CX Health Metrics

Static dashboard for the Product Health - CX metrics (B2I, Recharge-to-Exit, Closure
journeys), refreshed daily from Metabase/Snowflake and deployed on Vercel.

## How it works

- `metrics_config.json` — the 17 metric definitions (journey, name, description, SQL query).
- `refresh.py` — runs each query against Metabase, writes `dashboard_data.json`.
- `build.py` — renders `template.html` + `dashboard_data.json` into the static `index.html`.
- `.github/workflows/daily-refresh.yml` — runs the two scripts daily (02:00 UTC / 07:30 IST)
  and commits the result. Vercel is connected to this repo and auto-deploys on every push.

## Local development

```bash
export METABASE_KEY='mb_...'   # or rely on ~/Desktop/.env locally
python3 refresh.py
python3 build.py
open index.html
```

## Manual refresh

Trigger the "Daily metrics refresh" workflow from the Actions tab (workflow_dispatch)
to refresh on demand instead of waiting for the schedule.

## Adding a metric

Add an entry to `metrics_config.json` (id, journey, name, description, tbd, query),
matching the 9-window `D-1..M-3` output format the other queries use.
