# `scripts` folder

This folder contains **helper scripts** for the monorepo: development automation, maintenance utilities, repetitive tasks (setup, lint, migrations, data generation, etc.), and internal tooling.

- **Main purpose**: group support tools that do not belong to a specific app, agent, or pipeline but make the team’s work easier.
- **Recommendation**: document each script (what it does, parameters, requirements, usage examples) and keep them reproducible (and safe) across environments.

> _Spanish version: [README.es.md](./README.es.md)._

## `nightly_export.py` — nightly telemetry export + pipeline trigger

Daily background process: snapshots the previous UTC day of `telemetry_events`
to `data/raw/telemetry_<YYYY-MM-DD>.csv` (only if the file does not exist) and
then runs the business-performance pipeline as a subprocess
(`python data/pipelines/pipeline.py run --lookback 1 --json`).

Every attempt is a row in `job_runs`, and the row is the source of truth:

```
pending → processing → completed
                    ↘ failed
```

- `pending` is created **before** any work.
- `processing` is committed **before** the export starts.
- `completed` only after export + pipeline succeed.
- `failed` stores the diagnosis in `error_message`.
- Lock via `processing` (one run per job) and idempotency via
  (`job_name`, `target_date`) (one completed run per day).
- Orphan `processing` rows (killed process) are reconciled to `failed` before
  the lock check, so a crash never blocks the job forever.

### Usage

```bash
python scripts/nightly_export.py                    # yesterday (UTC)
TARGET_DATE=2026-10-29 python scripts/nightly_export.py
python scripts/nightly_export.py --target-date 2026-10-29
python scripts/nightly_export.py --dry-run          # prints the plan, writes nothing
python scripts/nightly_export.py --reconcile-only   # only recovers stale rows
```

Exit codes: `0` completed / skipped / blocked · `1` failed · `2` configuration error.

### Environment

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` (or `JOB_DATABASE_URL`) | — | DB where `job_runs` lives (same as the API) |
| `DATABASE_URL_PIPELINE` | `DATABASE_URL` | DB read by the pipeline subprocess |
| `TARGET_DATE` | yesterday UTC | Day to export (`YYYY-MM-DD`) |
| `JOB_STALE_MINUTES` | `60` | Age after which a `processing` row is an orphan |
| `PIPELINE_TIMEOUT_SECONDS` | `1800` | Subprocess timeout |
| `LOG_LEVEL` | `INFO` | Log level |

### Trigger (cron)

`scripts/crontab` is executed by supercronic inside the `scheduler` container:

```
CRON_TZ=UTC
15 2 * * * python /app/scripts/nightly_export.py
```

02:15 UTC because the UTC day already closed at 00:00 and there is margin for
telemetry ingestion; daily granularity because `target_date` is daily.
The job is **not** scheduled inside FastAPI (no APScheduler, no lifespan hooks).

```bash
docker compose up -d scheduler
docker compose logs -f scheduler
docker compose run --rm -e TARGET_DATE=2026-10-29 scheduler python /app/scripts/nightly_export.py
```

Host crontab is only an alternative for local runs without Docker:

```cron
15 2 * * * cd /path/to/repo && services/api/venv/bin/python scripts/nightly_export.py
```

### Tests

```bash
services/api/venv/bin/python -m pytest tests/jobs -q
```

### Logs

One line per event, UTC timestamp, job and resulting status:

```
2026-10-30T02:15:03Z level=INFO job=nightly_export status=pending target_date=2026-10-29 run_id=42 msg="registro creado antes de empezar el trabajo"
2026-10-30T02:15:04Z level=INFO job=nightly_export status=processing target_date=2026-10-29 run_id=42 msg="trabajo iniciado"
2026-10-30T02:15:22Z level=INFO job=nightly_export status=completed target_date=2026-10-29 run_id=42 rows=1843 pipeline_rc=0 msg="export + pipeline OK"
```
