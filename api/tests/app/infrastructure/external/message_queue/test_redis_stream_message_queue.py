import asyncio
import uuid

import pytest

from app.infrastructure.external.message_queue.redis_stream_message_queue import RedisStreamMessageQueue
from app.infrastructure.storage.redis import get_redis


async def _with_redis(scenario):
    redis = get_redis()
    try:
        await redis.init()
    except Exception as exc:
        pytest.skip(f"Redis不可用，跳过集成测试: {exc}")

    try:
        await scenario()
    finally:
        await redis.shutdown()


def test_pending_message_is_redelivered_until_ack():
    async def scenario():
        stream_name = f"test:stream:{uuid.uuid4()}"
        group_name = f"{stream_name}:group"
        queue = RedisStreamMessageQueue(
            stream_name=stream_name,
            consumer_group_name=group_name,
            consumer_name="consumer-a",
        )
        reconnect_queue = RedisStreamMessageQueue(
            stream_name=stream_name,
            consumer_group_name=group_name,
            consumer_name="consumer-a",
        )

        try:
            await queue.clear()

            message_id = await queue.put("hello")
            first_id, first_message = await queue.pop()
            assert (first_id, first_message) == (message_id, "hello")
            assert await queue.size() == 1

            replay_id, replay_message = await reconnect_queue.pop()
            assert (replay_id, replay_message) == (message_id, "hello")

            assert await reconnect_queue.ack(replay_id) is True
            assert await queue.is_empty() is True
        finally:
            await queue.clear()

    asyncio.run(_with_redis(scenario))


def test_ack_moves_consumer_group_to_next_message():
    async def scenario():
        stream_name = f"test:stream:{uuid.uuid4()}"
        group_name = f"{stream_name}:group"
        queue = RedisStreamMessageQueue(
            stream_name=stream_name,
            consumer_group_name=group_name,
            consumer_name="consumer-a",
        )

        try:
            await queue.clear()

            first_message_id = await queue.put("first")
            second_message_id = await queue.put("second")

            message_id, message = await queue.get()
            assert (message_id, message) == (first_message_id, "first")
            assert await queue.ack(message_id) is True

            next_message_id, next_message = await queue.get()
            assert (next_message_id, next_message) == (second_message_id, "second")
            assert await queue.ack(next_message_id) is True

            assert await queue.is_empty() is True
        finally:
            await queue.clear()

    asyncio.run(_with_redis(scenario))


def test_get_skips_last_delivered_event_id_on_reconnect():
    async def scenario():
        stream_name = f"test:stream:{uuid.uuid4()}"
        group_name = f"{stream_name}:group"
        queue = RedisStreamMessageQueue(
            stream_name=stream_name,
            consumer_group_name=group_name,
            consumer_name="consumer-a",
        )
        reconnect_queue = RedisStreamMessageQueue(
            stream_name=stream_name,
            consumer_group_name=group_name,
            consumer_name="consumer-a",
        )

        try:
            await queue.clear()

            first_message_id = await queue.put("first")
            second_message_id = await queue.put("second")

            delivered_id, delivered_message = await queue.get()
            assert (delivered_id, delivered_message) == (first_message_id, "first")

            resumed_id, resumed_message = await reconnect_queue.get(start_id=first_message_id)
            assert (resumed_id, resumed_message) == (second_message_id, "second")
            assert await reconnect_queue.ack(resumed_id) is True
            assert await reconnect_queue.is_empty() is True
        finally:
            await queue.clear()

    asyncio.run(_with_redis(scenario))
