"""Bus pub/sub por sesión: fan-out, aislamiento y publicación entre hilos."""

from __future__ import annotations

import asyncio
import threading

from app.chat.bus import ChatEventBus


def test_fan_out_to_every_subscriber_of_the_session() -> None:
    async def scenario() -> None:
        bus = ChatEventBus()
        loop = asyncio.get_running_loop()
        first = await bus.subscribe("chat_1", loop)
        second = await bus.subscribe("chat_1", loop)

        bus.publish("chat_1", "token_chunk", {"token": "Hola", "sequence": 1})

        assert (await asyncio.wait_for(first.get(), 1)).data["token"] == "Hola"
        assert (await asyncio.wait_for(second.get(), 1)).data["token"] == "Hola"

    asyncio.run(scenario())


def test_channels_are_isolated_per_session() -> None:
    async def scenario() -> None:
        bus = ChatEventBus()
        loop = asyncio.get_running_loop()
        first = await bus.subscribe("chat_1", loop)
        other = await bus.subscribe("chat_2", loop)

        bus.publish("chat_1", "token_chunk", {"token": "solo uno"})

        event = await asyncio.wait_for(first.get(), 1)
        assert event.data["token"] == "solo uno"
        with pytest_raises_timeout():
            await asyncio.wait_for(other.get(), 0.05)

    asyncio.run(scenario())


class pytest_raises_timeout:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return exc_type is asyncio.TimeoutError


def test_publish_from_another_thread_reaches_the_loop() -> None:
    async def scenario() -> None:
        bus = ChatEventBus()
        loop = asyncio.get_running_loop()
        subscription = await bus.subscribe("chat_1", loop)

        worker = threading.Thread(
            target=lambda: bus.publish(
                "chat_1", "token_chunk", {"token": "desde el productor"}
            )
        )
        worker.start()
        event = await asyncio.wait_for(subscription.get(), 1)
        worker.join()
        assert event.data["token"] == "desde el productor"

    asyncio.run(scenario())


def test_unsubscribe_stops_delivery_and_cleans_channel() -> None:
    async def scenario() -> None:
        bus = ChatEventBus()
        loop = asyncio.get_running_loop()
        subscription = await bus.subscribe("chat_1", loop)
        assert bus.subscriber_count("chat_1") == 1

        await bus.unsubscribe("chat_1", subscription)
        assert bus.subscriber_count("chat_1") == 0

        bus.publish("chat_1", "token_chunk", {"token": "nadie"})
        with pytest_raises_timeout():
            await asyncio.wait_for(subscription.get(), 0.05)

    asyncio.run(scenario())
