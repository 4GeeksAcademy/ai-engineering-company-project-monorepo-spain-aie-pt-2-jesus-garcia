"""Pandas pipeline for the operational telemetry report.

Every metric follows the same order: SQL load with push-down (``event_type``
and timestamp range) -> Pandas refine (``tags`` dimensions and derived
columns) -> UTC type conversion -> ``groupby`` -> aggregate -> ``list[dict]``.

The functions are read-only and deterministic for a given database state, so
the router can cache their output without side effects.
"""

import json
from datetime import datetime
from typing import Any, Iterable

import pandas as pd
from sqlmodel import Session, select

from models import TelemetryEventRecord, TelemetryEventType

ALL_EVENT_TYPES = tuple(event.value for event in TelemetryEventType)

FAILURE_EVENT_TYPES = (
    "direct_stock_edit_rejected",
    "stock_validation_failed",
    "outbound_rejected_insufficient_stock",
    "login_failed",
    "incident_validation_failed",
    "incident_transition_rejected",
    "frontend_error_uncaught",
)

LOGIN_FAILED = "login_failed"
LOGIN_SUCCEEDED = "login_succeeded"
LATENCY_EVENT = "api_response_time"

REPORT_METRIC_KEYS = (
    "events_per_day",
    "error_rate_by_day",
    "errors_by_type",
    "latency_per_day",
    "auth_failure_rate",
)

_FRAME_COLUMNS = ("event_type", "timestamp", "tags")


def fetch_events(
    session: Session,
    event_types: Iterable[str],
    start_date: datetime,
    end_date: datetime,
) -> list[dict[str, Any]]:
    """Load only the columns the metrics need, filtered in SQL.

    The date window is inclusive on ``start_date`` and exclusive on
    ``end_date``. ``event_type`` is always an ``IN`` predicate so the database
    never returns the full table.
    """

    statement = select(
        TelemetryEventRecord.event_type,
        TelemetryEventRecord.timestamp,
        TelemetryEventRecord.tags,
    ).where(
        TelemetryEventRecord.event_type.in_(list(event_types)),
        TelemetryEventRecord.timestamp >= start_date,
        TelemetryEventRecord.timestamp < end_date,
    )

    rows = session.exec(statement).all()
    return [
        {"event_type": event_type, "timestamp": timestamp, "tags": tags or {}}
        for event_type, timestamp, tags in rows
    ]


def _to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=_FRAME_COLUMNS)

    frame = pd.DataFrame(rows)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["date"] = frame["timestamp"].dt.strftime("%Y-%m-%d")
    return frame


def _tag_number(frame: pd.DataFrame, key: str) -> pd.Series:
    def extract(tags: Any) -> Any:
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except (TypeError, ValueError):
                return None
        if isinstance(tags, dict):
            return tags.get(key)
        return None

    return pd.to_numeric(frame["tags"].map(extract), errors="coerce")


def _records(frame: pd.DataFrame, sort_by: list[str]) -> list[dict[str, Any]]:
    return frame.sort_values(sort_by).to_dict(orient="records")


def events_per_day(
    session: Session,
    start_date: datetime,
    end_date: datetime,
) -> list[dict[str, Any]]:
    """Which event types occur, and how often, per UTC day."""

    frame = _to_frame(fetch_events(session, ALL_EVENT_TYPES, start_date, end_date))
    if frame.empty:
        return []

    grouped = (
        frame.groupby(["date", "event_type"], as_index=False)
        .size()
        .rename(columns={"size": "event_count"})
    )
    return _records(grouped, ["date", "event_count"])


def error_rate_by_day(
    session: Session,
    start_date: datetime,
    end_date: datetime,
) -> list[dict[str, Any]]:
    """Failures relative to total events per UTC day."""

    frame = _to_frame(fetch_events(session, ALL_EVENT_TYPES, start_date, end_date))
    if frame.empty:
        return []

    frame["is_failure"] = frame["event_type"].isin(FAILURE_EVENT_TYPES)
    grouped = frame.groupby("date", as_index=False).agg(
        event_count=("event_type", "size"),
        error_count=("is_failure", "sum"),
    )
    grouped["error_count"] = grouped["error_count"].astype(int)
    grouped["error_rate"] = (
        grouped["error_count"] / grouped["event_count"]
    ).round(4)
    return _records(grouped, ["date"])


def errors_by_type(
    session: Session,
    start_date: datetime,
    end_date: datetime,
) -> list[dict[str, Any]]:
    """Where failure signals concentrate, per UTC day and event type."""

    frame = _to_frame(
        fetch_events(session, FAILURE_EVENT_TYPES, start_date, end_date)
    )
    if frame.empty:
        return []

    grouped = (
        frame.groupby(["date", "event_type"], as_index=False)
        .size()
        .rename(columns={"size": "error_count"})
    )
    return _records(grouped, ["date", "error_count"])


def latency_per_day(
    session: Session,
    start_date: datetime,
    end_date: datetime,
) -> list[dict[str, Any]]:
    """API response latency per UTC day, from ``api_response_time`` events."""

    frame = _to_frame(fetch_events(session, (LATENCY_EVENT,), start_date, end_date))
    if frame.empty:
        return []

    frame["duration_ms"] = _tag_number(frame, "duration_ms")
    frame = frame.dropna(subset=["duration_ms"])
    if frame.empty:
        return []

    grouped = frame.groupby("date", as_index=False).agg(
        avg_ms=("duration_ms", "mean"),
        p50_ms=("duration_ms", "median"),
        p95_ms=("duration_ms", lambda values: values.quantile(0.95)),
        sample_count=("duration_ms", "size"),
    )
    for column in ("avg_ms", "p50_ms", "p95_ms"):
        grouped[column] = grouped[column].round(1)
    grouped["sample_count"] = grouped["sample_count"].astype(int)
    return _records(grouped, ["date"])


def auth_failure_rate(
    session: Session,
    start_date: datetime,
    end_date: datetime,
) -> list[dict[str, Any]]:
    """Failed logins over all login attempts per UTC day (0.0 to 1.0)."""

    frame = _to_frame(
        fetch_events(
            session,
            (LOGIN_FAILED, LOGIN_SUCCEEDED),
            start_date,
            end_date,
        )
    )
    if frame.empty:
        return []

    counts = (
        frame.groupby(["date", "event_type"], as_index=False)
        .size()
        .rename(columns={"size": "count"})
    )
    pivot = counts.pivot(
        index="date", columns="event_type", values="count"
    ).fillna(0)
    for event_type in (LOGIN_FAILED, LOGIN_SUCCEEDED):
        if event_type not in pivot.columns:
            pivot[event_type] = 0

    pivot = pivot[[LOGIN_FAILED, LOGIN_SUCCEEDED]].astype(int).reset_index()
    attempts = pivot[LOGIN_FAILED] + pivot[LOGIN_SUCCEEDED]
    pivot["failure_rate"] = (pivot[LOGIN_FAILED] / attempts).round(4)
    pivot = pivot.rename(
        columns={LOGIN_FAILED: "failed", LOGIN_SUCCEEDED: "succeeded"}
    )
    return _records(
        pivot[["date", "failed", "succeeded", "failure_rate"]], ["date"]
    )


def build_metrics(
    session: Session,
    start_date: datetime,
    end_date: datetime,
) -> dict[str, list[dict[str, Any]]]:
    """Run every metric function for the same period."""

    return {
        "events_per_day": events_per_day(session, start_date, end_date),
        "error_rate_by_day": error_rate_by_day(session, start_date, end_date),
        "errors_by_type": errors_by_type(session, start_date, end_date),
        "latency_per_day": latency_per_day(session, start_date, end_date),
        "auth_failure_rate": auth_failure_rate(session, start_date, end_date),
    }
