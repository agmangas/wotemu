import json
import logging
from datetime import datetime, timezone

import aioredis
import pandas as pd
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

    async def _get_zrange_df(self, key):
        members = await self._client.zrange(key=key)
        rows = [json.loads(item) for item in members]

        [
            row.update({
                "date": datetime.fromtimestamp(row["time"], timezone.utc)
            })
            for row in rows
        ]

        df = pd.DataFrame(rows)
        df.set_index("date", inplace=True)

        return df

    async def get_nodes(self):
        pattern = "{}:{}:*".format(
            RedisPrefixes.NAMESPACE.value,
            RedisPrefixes.INFO.value)

        keys = await self._client.keys(pattern=pattern)

        return {key.decode().split(":")[-1] for key in keys}

    async def get_system_df(self, node):
        key = "{}:{}:{}".format(
            RedisPrefixes.NAMESPACE.value,
            RedisPrefixes.SYSTEM.value,
            node)

        return await self._get_zrange_df(key=key)

    async def get_packet_df(self, node):
        pattern = "{}:{}:*:{}".format(
            RedisPrefixes.NAMESPACE.value,
            RedisPrefixes.PACKET.value,
            node)

        packet_keys = await self._client.keys(pattern=pattern)

        dfs = []

        for key in packet_keys:
            iface = key.decode().split(":")[2]
            df_iface = await self._get_zrange_df(key=key)
            df_iface["iface"] = iface
            df_iface.set_index(["iface"], append=True, inplace=True)
            dfs.append(df_iface)

        df_concat = pd.concat(dfs)
        df_concat.sort_index(inplace=True)

        return df_concat
