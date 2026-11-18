"""Tests del bus de eventos (contrato que consume el endpoint SSE)."""

from __future__ import annotations

import asyncio
import threading

import pytest

from app.realtime.broker import Event, LocalBroker


@pytest.fixture(autouse=True)
def _reset_global_broker():
    from app.realtime.broker import reset_broker

    reset_broker()
    yield
    reset_broker()


def test_publish_fans_out_to_every_subscriber():
    async def scenario() -> None:
        broker = LocalBroker()
        loop = asyncio.get_running_loop()
        first = await broker.subscribe(loop)
        second = await broker.subscribe(loop)

        event = broker.publish("rfp_ticket_created", {"ticket_id": "t1"})

        assert isinstance(event, Event)
        assert event.id == 1
        assert await first.get(timeout=1) == event
        assert await second.get(timeout=1) == event

    asyncio.run(scenario())


def test_replay_returns_only_events_after_the_cursor():
    broker = LocalBroker()
    first = broker.publish("rfp_ticket_created", {"ticket_id": "t1"})
    second = broker.publish("rfp_ticket_created", {"ticket_id": "t2"})
    third = broker.publish("sla_threshold_alert", {"alert_id": "sla:1:US"})

    assert broker.replay_after(None) == []
    assert [event.id for event in broker.replay_after(first.id)] == [
        second.id,
        third.id,
    ]
    assert broker.replay_after(third.id) == []


def test_slow_subscriber_drops_oldest_and_reports_lag():
    async def scenario() -> None:
        broker = LocalBroker(queue_size=2)
        loop = asyncio.get_running_loop()
        subscription = await broker.subscribe(loop)

        broker.publish("rfp_ticket_created", {"ticket_id": "t1"})
        broker.publish("rfp_ticket_created", {"ticket_id": "t2"})
        broker.publish("rfp_ticket_created", {"ticket_id": "t3"})
        await asyncio.sleep(0)

        assert subscription.take_dropped() == 1
        remaining = [
            (await subscription.get(timeout=1)).data["ticket_id"]  # type: ignore[union-attr]
            for _ in range(2)
        ]
        assert remaining == ["t2", "t3"]
        assert subscription.take_dropped() == 0

    asyncio.run(scenario())


def test_publish_is_safe_from_another_thread():
    async def scenario() -> None:
        broker = LocalBroker()
        loop = asyncio.get_running_loop()
        subscription = await broker.subscribe(loop)

        worker = threading.Thread(
            target=broker.publish,
            args=("rfp_ticket_created", {"ticket_id": "t9"}),
        )
        worker.start()
        worker.join(timeout=2)

        event = await subscription.get(timeout=1)
        assert event is not None
        assert event.data["ticket_id"] == "t9"

    asyncio.run(scenario())


def test_event_json_roundtrip_keeps_id_name_and_data():
    event = Event(7, "rfp_ticket_created", {"ticket_id": "t1", "status": "analizando"})
    restored = Event.from_json(event.to_json())
    assert restored == event
