import json
import logging

import aioredis
from wotemu.enums import RedisPrefixes

_logger = logging.getLogger(__name__)


class ReportDataRedisReader:
    def __init__(self, redis_url):
        self._redis_url = redis_url
        self._client = None

    async def connect(self):
        await self.close()
        self._client = await aioredis.create_redis_pool(self._redis_url)

    async def close(self):
        if self._client is None:
            return

        try:
            self._client.close()
            await self._client.wait_closed()
        except Exception as ex:
            _logger.warning("Error closing connection: %s", ex)
        finally:
            self._client = None

    async def get_nodes(self):
        pattern = "{}:{}:*".format(
            RedisPrefixes.NAMESPACE.value,
            RedisPrefixes.INFO.value)

        keys = await self._client.keys(pattern=pattern)

        return {key.decode().split(":")[-1] for key in keys}
