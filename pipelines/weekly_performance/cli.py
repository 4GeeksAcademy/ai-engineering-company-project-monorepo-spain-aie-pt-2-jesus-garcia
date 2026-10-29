"""Ejecución del pipeline por script, sin depender de un servidor Prefect.

Ejemplos::

    python -m pipelines.weekly_performance run --lookback 3
    python -m pipelines.weekly_performance backfill --week 2026-07-13
    python -m pipelines.weekly_performance backfill --week 2026-07-13 \\
        --force --reason "corrección de evento tardío"
    python -m pipelines.weekly_performance replay --run-id <uuid>
    python -m pipelines.weekly_performance relay --batch-size 100
    python -m pipelines.weekly_performance watchdog
"""

from __future__ import annotations

import argparse
from datetime import date
import json
import sys

from .core import (
    freeze_week,
    mark_zombie_runs,
    replay_rejects,
    resolve_target_weeks,
    run_week,
)
from .db import get_engine
from .outbox import relay_outbox
from .settings import DEFAULT_LOOKBACK_WEEKS, get_instrumentation_since
from .sql import create_reporting_schema


def _parse_date(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"fecha inválida: {value}") from exc
    if parsed.isoweekday() != 1:
        raise argparse.ArgumentTypeError(f"{value} no es lunes")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pipelines.weekly_performance",
        description="Pipeline semanal de desempeño por almacén y cliente.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="Procesa la última semana cerrada y el lookback."
    )
    run_parser.add_argument(
        "--lookback",
        type=int,
        default=DEFAULT_LOOKBACK_WEEKS,
        help="Número de semanas cerradas a recalcular (1-12).",
    )
    run_parser.add_argument(
        "--week",
        type=_parse_date,
        help="Procesa solo esta semana (lunes ISO).",
    )
    run_parser.add_argument("--force", action="store_true")
    run_parser.add_argument("--reason", default=None)
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--json", action="store_true", dest="as_json")

    backfill_parser = subparsers.add_parser(
        "backfill", help="Reprocesa una semana concreta con el mismo flujo."
    )
    backfill_parser.add_argument("--week", type=_parse_date, required=True)
    backfill_parser.add_argument("--force", action="store_true")
    backfill_parser.add_argument("--reason", default=None)
    backfill_parser.add_argument("--dry-run", action="store_true")
    backfill_parser.add_argument("--json", action="store_true", dest="as_json")

    replay_parser = subparsers.add_parser(
        "replay", help="Reprocesa la semana de una corrida con rechazos."
    )
    replay_parser.add_argument("--run-id", required=True)
    replay_parser.add_argument("--json", action="store_true", dest="as_json")

    relay_parser = subparsers.add_parser(
        "relay", help="Mueve eventos pendientes del outbox a telemetría."
    )
    relay_parser.add_argument("--batch-size", type=int, default=100)
    relay_parser.add_argument("--json", action="store_true", dest="as_json")

    freeze_parser = subparsers.add_parser(
        "freeze", help="Congela una semana para que el lookback no la reescriba."
    )
    freeze_parser.add_argument("--week", type=_parse_date, required=True)
    freeze_parser.add_argument("--by", default="manual")
    freeze_parser.add_argument("--json", action="store_true", dest="as_json")

    watchdog_parser = subparsers.add_parser(
        "watchdog", help="Marca como failed las corridas running sin latido."
    )
    watchdog_parser.add_argument("--max-age-minutes", type=int, default=120)
    watchdog_parser.add_argument("--json", action="store_true", dest="as_json")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if getattr(args, "force", False) and not args.reason:
        parser.error("--force requiere --reason para dejar auditoría")

    if args.command == "relay":
        engine = get_engine()
        create_reporting_schema(engine)
        result = relay_outbox(engine, batch_size=args.batch_size)
        payload = {"relayed": result.relayed, "duplicates": result.duplicates}
        print(json.dumps(payload, indent=2) if args.as_json else payload)
        return 0

    if args.command == "watchdog":
        engine = get_engine()
        create_reporting_schema(engine)
        marked = mark_zombie_runs(engine, max_age_minutes=args.max_age_minutes)
        payload = {"marked_failed": marked}
        print(json.dumps(payload, indent=2) if args.as_json else payload)
        return 0

    engine = get_engine()
    create_reporting_schema(engine)

    if args.command == "replay":
        result = replay_rejects(engine, args.run_id)
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.status in {"success", "skipped"} else 1

    if args.command == "freeze":
        freeze_week(engine, args.week, published_by=args.by)
        payload = {"week_start": args.week.isoformat(), "frozen": True}
        print(json.dumps(payload, indent=2) if args.as_json else payload)
        return 0

    weeks = (
        [args.week]
        if args.week is not None
        else resolve_target_weeks(args.lookback)
    )

    if args.dry_run:
        payload = {
            "command": args.command,
            "weeks": [week.isoformat() for week in weeks],
            "force": args.force,
            "reason": args.reason,
        }
        print(json.dumps(payload, indent=2))
        return 0

    results = [
        run_week(
            engine,
            week,
            triggered_by=args.command,
            force=args.force,
            reason=args.reason,
            instrumentation_since=get_instrumentation_since(),
        )
        for week in weeks
    ]

    payload = [result.to_dict() for result in results]
    if args.as_json:
        print(json.dumps(payload, indent=2))
    else:
        for result in results:
            print(
                f"{result.week_start}  {result.status:<8} "
                f"extraídas={result.rows_extracted:<5} "
                f"válidas={result.rows_valid:<5} "
                f"rechazadas={result.rows_rejected:<3} "
                f"escritas={result.rows_written:<3} "
                f"calidad={result.quality_status or '-'}"
                + (f"  error={result.error}" if result.error else "")
            )

    return 0 if all(r.status in {"success", "skipped"} for r in results) else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
