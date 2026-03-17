import logging
from typing import Any, AsyncGenerator, Optional, Tuple

from redis.exceptions import ResponseError

from app.domain.external.message_queue import MessageQueue
from app.infrastructure.storage.redis import get_redis

logger = logging.getLogger(__name__)


class RedisStreamMessageQueue(MessageQueue):
    """基于Redis Stream Consumer Group的消息队列"""

    def __init__(
            self,
            stream_name: str,
            consumer_group_name: Optional[str] = None,
            consumer_name: Optional[str] = None,
    ) -> None:
        self._stream_name = stream_name
        self._redis = get_redis()
        self._consumer_group_name = consumer_group_name or f"{stream_name}:group"
        self._consumer_name = consumer_name or f"{stream_name}:consumer"

    async def _ensure_consumer_group(self) -> None:
        """确保当前stream对应的consumer group存在"""
        try:
            await self._redis.client.xgroup_create(
                name=self._stream_name,
                groupname=self._consumer_group_name,
                id="0",
                mkstream=True,
            )
            logger.info(
                "Redis Stream Consumer Group已创建: stream=%s group=%s",
                self._stream_name,
                self._consumer_group_name,
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    @staticmethod
    def _parse_messages(messages: list) -> Tuple[Optional[str], Any]:
        """从Redis Stream响应中提取一条消息"""
        if not messages:
            return None, None

        stream_messages = messages[0][1]
        if not stream_messages:
            return None, None

        message_id, message_data = stream_messages[0]
        return message_id, message_data.get("data")

    async def _read_from_group(self, block_ms: int = None) -> Tuple[Optional[str], Any]:
        """优先读取当前consumer的pending消息，没有则继续读取新消息"""
        await self._ensure_consumer_group()

        pending_messages = await self._redis.client.xreadgroup(
            groupname=self._consumer_group_name,
            consumername=self._consumer_name,
            streams={self._stream_name: "0"},
            count=1,
        )
        message_id, message = self._parse_messages(pending_messages)
        if message_id is not None:
            return message_id, message

        messages = await self._redis.client.xreadgroup(
            groupname=self._consumer_group_name,
            consumername=self._consumer_name,
            streams={self._stream_name: ">"},
            count=1,
            block=block_ms,
        )
        return self._parse_messages(messages)

    async def put(self, message: Any) -> str:
        """往redis-stream中添加一条消息并返回id"""
        logger.debug("往消息队列[%s]中添加一条消息", self._stream_name)
        return await self._redis.client.xadd(self._stream_name, {"data": message})

    async def get(self, start_id: str = None, block_ms: int = None) -> Tuple[str, Any]:
        """从redis-stream获取一条数据，成功消费后需要显式ACK"""
        logger.debug("从消息队列[%s]中获取一条消息", self._stream_name)

        try:
            while True:
                message_id, message = await self._read_from_group(block_ms=block_ms)
                if message_id is None:
                    return None, None

                # SSE重连时，客户端会把最后一个已收到的event_id带回来。
                # 这时如果该消息仍处于pending，需要先ACK后再继续读取下一条，避免重复投递。
                if start_id and message_id == start_id:
                    await self.ack(message_id)
                    start_id = None
                    continue

                return message_id, message
        except Exception as exc:
            logger.error("从消息队列[%s]获取数据失败: %s", self._stream_name, exc)
            return None, None

    async def pop(self) -> Tuple[str, Any]:
        """消费消息队列中的第一条消息，成功处理后需要显式ACK"""
        logger.debug("从消息队列[%s]中消费第一条消息", self._stream_name)

        try:
            return await self._read_from_group()
        except Exception as exc:
            logger.error("消费消息队列[%s]失败: %s", self._stream_name, exc)
            return None, None

    async def ack(self, message_id: str) -> bool:
        """确认指定消息已被成功处理，并从stream中删除"""
        if not message_id:
            return False

        try:
            await self._ensure_consumer_group()
            await self._redis.client.xack(
                self._stream_name,
                self._consumer_group_name,
                message_id,
            )
            await self._redis.client.xdel(self._stream_name, message_id)
            return True
        except Exception as exc:
            logger.error("确认消息[%s]失败: stream=%s error=%s", message_id, self._stream_name, exc)
            return False

    async def clear(self) -> None:
        """清除redis-stream中的所有消息和consumer group状态"""
        await self._redis.client.delete(self._stream_name)

    async def is_empty(self) -> bool:
        """检查redis-stream是否为空"""
        return await self.size() == 0

    async def size(self) -> int:
        """获取redis-stream的长度"""
        return await self._redis.client.xlen(self._stream_name)

    async def delete_message(self, message_id: str) -> bool:
        """根据传递的消息id从redis-stream删除数据"""
        try:
            await self._redis.client.xack(
                self._stream_name,
                self._consumer_group_name,
                message_id,
            )
            await self._redis.client.xdel(self._stream_name, message_id)
            return True
        except Exception:
            return False

    async def get_range(
            self,
            start_id: str = "-",
            end_id: str = "+",
            count: int = 100,
    ) -> AsyncGenerator[Tuple[str, Any], None]:
        """根据传递的起点、终点id、数量，获取异步迭代器得到消息数据"""
        messages = await self._redis.client.xrange(self._stream_name, start_id, end_id, count=count)
        if not messages:
            return

        for message_id, message_data in messages:
            try:
                yield message_id, message_data.get("data")
            except Exception:
                continue

    async def get_latest_id(self) -> str:
        """获取消息队列中最新的id"""
        messages = await self._redis.client.xrevrange(self._stream_name, "+", "-", count=1)
        if not messages:
            return "0"

        return messages[0][0]
