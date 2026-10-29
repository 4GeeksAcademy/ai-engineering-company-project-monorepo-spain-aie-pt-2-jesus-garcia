from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import event, delete
from sqlmodel import Session, SQLModel, select

import app.telemetry.analysis as analysis
from database import engine
from models import TelemetryEventRecord


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 6, day, hour, minute, tzinfo=timezone.utc)


def make_record(
    event_type: str,
    timestamp: datetime,
    tags: dict | None = None,
) -> TelemetryEventRecord:
    return TelemetryEventRecord(
        event_id=str(uuid4()),
        timestamp=timestamp,
        event_type=event_type,
        service="backoffice",
        session_id="session-report",
        schema_version="1.0.0",
        source="backend",
        tags=tags or {},
    )


@pytest.fixture(autouse=True)
def _clean_telemetry_events():
    SQLModel.metadata.create_all(engine)

    def clear() -> None:
        with Session(engine) as session:
            session.exec(delete(TelemetryEventRecord))
            session.commit()

    clear()
    yield
    clear()


@pytest.fixture()
def seeded_events() -> None:
    records = [
        make_record("inbound_order_created", _at(14, 9), {"warehouse": "los_angeles"}),
        make_record("outbound_order_created", _at(14, 10), {"warehouse": "zaragoza"}),
        make_record("api_response_time", _at(14, 11), {"duration_ms": 100}),
        make_record("api_response_time", _at(14, 12), {"duration_ms": 300}),
        make_record("login_failed", _at(14, 13)),
        make_record("login_succeeded", _at(14, 14)),
        make_record("page_view", _at(15, 9), {"path": "/inventory"}),
        make_record("frontend_error_uncaught", _at(15, 10), {"path": "/inventory"}),
        make_record("login_failed", _at(15, 11)),
        make_record("api_response_time", _at(15, 12), {"duration_ms": 50}),
        make_record("api_response_time", _at(13, 23), {"duration_ms": 999}),
        make_record("login_failed", _at(16, 1)),
    ]
    with Session(engine) as session:
        session.add_all(records)
        session.commit()


def _metric(name: str) -> list[dict]:
    with Session(engine) as session:
        return getattr(analysis, name)(
            session,
            datetime(2026, 6, 14, tzinfo=timezone.utc),
            datetime(2026, 6, 16, tzinfo=timezone.utc),
        )


def _report(client) -> dict:
    response = client.get(
        "/telemetry/report",
        params={
            "start_date": "2026-06-14T00:00:00Z",
            "end_date": "2026-06-16T00:00:00Z",
        },
    )
    assert response.status_code == 200
    return response.json()


class TestAnalysisMetrics:
    def test_events_per_day_groups_by_date_and_event_type(self, seeded_events):
        rows = _metric("events_per_day")

        day14 = {
            row["event_type"]: row["event_count"]
            for row in rows
            if row["date"] == "2026-06-14"
        }
        day15 = {
            row["event_type"]: row["event_count"]
            for row in rows
            if row["date"] == "2026-06-15"
        }

        assert day14 == {
            "inbound_order_created": 1,
            "outbound_order_created": 1,
            "api_response_time": 2,
            "login_failed": 1,
            "login_succeeded": 1,
        }
        assert day15 == {
            "page_view": 1,
            "frontend_error_uncaught": 1,
            "login_failed": 1,
            "api_response_time": 1,
        }

    def test_error_rate_by_day(self, seeded_events):
        rows = _metric("error_rate_by_day")

        assert rows == [
            {
                "date": "2026-06-14",
                "event_count": 6,
                "error_count": 1,
                "error_rate": 0.1667,
            },
            {
                "date": "2026-06-15",
                "event_count": 4,
                "error_count": 2,
                "error_rate": 0.5,
            },
        ]

    def test_errors_by_type(self, seeded_events):
        rows = _metric("errors_by_type")

        assert rows == [
            {"date": "2026-06-14", "event_type": "login_failed", "error_count": 1},
            {
                "date": "2026-06-15",
                "event_type": "frontend_error_uncaught",
                "error_count": 1,
            },
            {"date": "2026-06-15", "event_type": "login_failed", "error_count": 1},
        ]

    def test_latency_per_day(self, seeded_events):
        rows = _metric("latency_per_day")

        assert rows == [
            {
                "date": "2026-06-14",
                "avg_ms": 200.0,
                "p50_ms": 200.0,
                "p95_ms": 290.0,
                "sample_count": 2,
            },
            {
                "date": "2026-06-15",
                "avg_ms": 50.0,
                "p50_ms": 50.0,
                "p95_ms": 50.0,
                "sample_count": 1,
            },
        ]

    def test_auth_failure_rate(self, seeded_events):
        rows = _metric("auth_failure_rate")

        assert rows == [
            {
                "date": "2026-06-14",
                "failed": 1,
                "succeeded": 1,
                "failure_rate": 0.5,
            },
            {
                "date": "2026-06-15",
                "failed": 1,
                "succeeded": 0,
                "failure_rate": 1.0,
            },
        ]

    def test_timestamps_are_converted_before_grouping(self, seeded_events):
        rows = _metric("events_per_day")

        assert {row["date"] for row in rows} == {"2026-06-14", "2026-06-15"}

    def test_empty_period_returns_empty_lists(self, seeded_events):
        with Session(engine) as session:
            metrics = analysis.build_metrics(
                session,
                datetime(2026, 6, 20, tzinfo=timezone.utc),
                datetime(2026, 6, 21, tzinfo=timezone.utc),
            )

        assert metrics == {
            "events_per_day": [],
            "error_rate_by_day": [],
            "errors_by_type": [],
            "latency_per_day": [],
            "auth_failure_rate": [],
        }

    def test_event_type_and_timestamp_are_pushed_down_to_sql(self, seeded_events):
        with Session(engine) as session:
            rows = analysis.fetch_events(
                session,
                ("login_failed",),
                _at(15, 0),
                datetime(2026, 6, 16, tzinfo=timezone.utc),
            )

        assert [row["event_type"] for row in rows] == ["login_failed"]
        timestamp = rows[0]["timestamp"]
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        assert timestamp == _at(15, 11)


class TestReportEndpoint:
    def test_response_has_period_and_five_metrics(self, client, seeded_events):
        body = _report(client)

        assert body["period"] == {
            "from": "2026-06-14T00:00:00Z",
            "to": "2026-06-16T00:00:00Z",
        }
        assert set(body["metrics"]) == set(analysis.REPORT_METRIC_KEYS)
        assert body["metrics"]["error_rate_by_day"][0]["date"] == "2026-06-14"

    def test_default_period_is_last_seven_days(self, client):
        body = client.get("/telemetry/report").json()

        start = datetime.fromisoformat(
            body["period"]["from"].replace("Z", "+00:00")
        )
        end = datetime.fromisoformat(body["period"]["to"].replace("Z", "+00:00"))

        assert end - start == timedelta(days=7)
        assert set(body["metrics"]) == set(analysis.REPORT_METRIC_KEYS)

    def test_end_date_is_exclusive(self, client, seeded_events):
        body = client.get(
            "/telemetry/report",
            params={
                "start_date": "2026-06-14T00:00:00Z",
                "end_date": "2026-06-15T00:00:00Z",
            },
        ).json()

        dates = {row["date"] for row in body["metrics"]["events_per_day"]}
        assert dates == {"2026-06-14"}

    def test_invalid_period_returns_400(self, client):
        response = client.get(
            "/telemetry/report",
            params={
                "start_date": "2026-06-16T00:00:00Z",
                "end_date": "2026-06-14T00:00:00Z",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "start_date must be before end_date"

    def test_repeated_report_is_served_from_cache(self, client, seeded_events, monkeypatch):
        calls = {"count": 0}
        original = analysis.build_metrics

        def spy(*args, **kwargs):
            calls["count"] += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(analysis, "build_metrics", spy)
        params = {
            "start_date": "2026-06-14T00:00:00Z",
            "end_date": "2026-06-16T00:00:00Z",
        }

        first = client.get("/telemetry/report", params=params).json()
        second = client.get("/telemetry/report", params=params).json()

        assert calls["count"] == 1
        assert first == second

    def test_report_selects_with_event_type_in_and_timestamp_range(self, client, seeded_events):
        statements: list[str] = []

        def capture(conn, cursor, statement, parameters, context, executemany):
            if statement.lstrip().upper().startswith("SELECT"):
                statements.append(statement)

        event.listen(engine, "before_cursor_execute", capture)
        try:
            _report(client)
        finally:
            event.remove(engine, "before_cursor_execute", capture)

        normalized = [statement.upper() for statement in statements]
        assert any(
            "EVENT_TYPE IN" in statement and "TIMESTAMP >=" in statement
            for statement in normalized
        )
