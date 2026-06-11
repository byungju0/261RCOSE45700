from __future__ import annotations

import asyncio

from crawler.src.scheduler import trigger_listener
from crawler.src.scheduler.trigger_listener import TriggerListener


async def test_trigger_listener_disables_pubsub_read_timeout(monkeypatch):
    captured_kwargs = {}
    subscribed = asyncio.Event()

    class FakePubSub:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def subscribe(self, channel):
            subscribed.set()

        async def listen(self):
            yield {"type": "subscribe"}
            await asyncio.Event().wait()

    class FakeRedis:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        def pubsub(self):
            return FakePubSub()

        async def setex(self, key, ttl, value):
            return True

    def fake_from_url(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return FakeRedis()

    monkeypatch.setattr(trigger_listener.aioredis, "from_url", fake_from_url)
    listener = TriggerListener("redis://redis:6379", lambda command: None)  # type: ignore[arg-type]

    task = asyncio.create_task(listener.listen())
    try:
        await asyncio.wait_for(subscribed.wait(), timeout=1)
        assert captured_kwargs["socket_timeout"] is None
        assert captured_kwargs["socket_connect_timeout"] == 5
        assert captured_kwargs["health_check_interval"] == 30
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
