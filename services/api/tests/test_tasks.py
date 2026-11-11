import pytest
from sqlalchemy import delete
from sqlmodel import Session, select

from app.incidents import service as incidents_service
from app.tasks import incidents as incidents_task
from app.tasks.dlq import record_dead_letter
from database import engine
from models import DeadLetterTask


@pytest.fixture(autouse=True)
def _clean_dlq():
    if engine is not None:
        from sqlmodel import SQLModel

        import models  # noqa: F401

        SQLModel.metadata.create_all(engine)
        with Session(engine) as session:
            session.exec(delete(DeadLetterTask))
            session.commit()
    yield


def _boom(_path):
    raise RuntimeError("boom")


def test_celery_task_configuration():
    from celery_app import celery_app

    assert incidents_task.analyze_incidents_csv.max_retries == 3
    assert celery_app.conf.task_track_started is True
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.task_time_limit == 600
    assert celery_app.conf.task_soft_time_limit == 540


def test_task_analyzes_csv_and_removes_file(tmp_path, sample_csv_bytes):
    path = tmp_path / "sample.csv"
    path.write_bytes(sample_csv_bytes)

    result = incidents_task.analyze_incidents_csv.run(
        str(path), "sample.csv"
    )

    assert result["total"] == 5
    assert result["valid"] == 5
    assert not path.exists()


def test_task_retries_with_exponential_backoff(tmp_path, monkeypatch):
    path = tmp_path / "bad.csv"
    path.write_bytes(b"not,a,valid,header\n")
    monkeypatch.setattr(incidents_service, "analyze_path", _boom)

    countdowns: list[float] = []

    def fake_retry(*, exc, countdown):
        countdowns.append(countdown)
        raise RuntimeError("retry-called")

    monkeypatch.setattr(
        incidents_task.analyze_incidents_csv, "retry", fake_retry
    )

    with pytest.raises(RuntimeError, match="retry-called"):
        incidents_task.analyze_incidents_csv.run(str(path), "bad.csv")

    assert countdowns == [5.0]


def test_task_records_dead_letter_after_max_retries(tmp_path, monkeypatch):
    path = tmp_path / "bad.csv"
    path.write_bytes(b"not,a,valid,header\n")
    monkeypatch.setattr(incidents_service, "analyze_path", _boom)

    captured: dict = {}
    monkeypatch.setattr(
        incidents_task,
        "record_dead_letter",
        lambda **kwargs: captured.update(kwargs),
    )
    monkeypatch.setattr(
        incidents_task.analyze_incidents_csv.request, "retries", 3
    )
    monkeypatch.setattr(incidents_task.analyze_incidents_csv.request, "id", "task-123")

    with pytest.raises(RuntimeError, match="boom"):
        incidents_task.analyze_incidents_csv.run(str(path), "bad.csv")

    assert captured == {
        "task_id": "task-123",
        "task_name": "incidents.analyze_csv",
        "attempts": 4,
        "max_retries": 3,
        "error_message": "RuntimeError: boom",
    }
    assert path.exists()


def test_record_dead_letter_persists_sql_and_redis(monkeypatch):
    pushed: list[tuple[str, str]] = []

    class FakeRedis:
        def rpush(self, key, value):
            pushed.append((key, value))

    monkeypatch.setattr(
        "app.tasks.dlq._redis_client", lambda: FakeRedis()
    )

    record_dead_letter(
        task_id="task-dlq",
        task_name="incidents.analyze_csv",
        attempts=4,
        max_retries=3,
        error_message="RuntimeError: boom",
    )

    with Session(engine) as session:
        row = session.exec(
            select(DeadLetterTask).where(
                DeadLetterTask.task_id == "task-dlq"
            )
        ).first()

    assert row is not None
    assert row.task_name == "incidents.analyze_csv"
    assert row.attempts == 4
    assert row.max_retries == 3
    assert row.error_message == "RuntimeError: boom"
    assert row.created_at is not None

    assert len(pushed) == 1
    assert pushed[0][0] == "dlq:trackflow"
    assert '"task_id": "task-dlq"' in pushed[0][1]


@pytest.mark.parametrize(
    ("state", "expected", "payload"),
    [
        ("PENDING", "pending", None),
        ("RECEIVED", "pending", None),
        ("STARTED", "started", None),
        ("RETRY", "started", None),
        ("SUCCESS", "success", {"total": 1}),
        ("FAILURE", "failure", "RuntimeError: boom"),
    ],
)
def test_get_task_status_maps_celery_states(
    client, auth_headers, monkeypatch, state, expected, payload
):
    class FakeResult:
        def __init__(self):
            self.state = state
            self.result = payload

    monkeypatch.setattr(
        "app.routes.tasks.AsyncResult",
        lambda task_id, app: FakeResult(),
    )

    response = client.get("/tasks/task-abc", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["task_id"] == "task-abc"
    assert body["status"] == expected
    assert body["result"] == payload


def test_get_task_status_requires_auth(client):
    response = client.get("/tasks/task-abc")
    assert response.status_code == 401
