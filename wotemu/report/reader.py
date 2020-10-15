import functools
import json
import logging
import socket
from datetime import datetime, timezone

import aioredis
import numpy as np
import pandas as pd
from wotemu.enums import RedisPrefixes
from wotemu.topology.compose import ENV_KEY_SERVICE_NAME

_IFACE_LO = "lo"

_logger = logging.getLogger(__name__)


def _explode_mapper(val, key):
    if val is np.nan:
        return np.nan

    try:
        return val[key]
    except:
        return np.nan


def _unique_keys_dict_column(df, col):
    dict_filter = df[col].apply(lambda x: isinstance(x, dict))
    keys = df[dict_filter][col].apply(tuple).unique()

    # Flatten list of tuples:
    # https://stackoverflow.com/a/10636583
    keys = set(sum(keys, ()))

    return keys


def explode_dict_column(df, col):
    if col not in df:
        return

    keys = _unique_keys_dict_column(df, col)

    for key in keys:
        mapper = functools.partial(_explode_mapper, key=key)
        df[f"{col}_{key}"] = df[col].apply(mapper)


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

        for row in rows:
            row_date = datetime.fromtimestamp(row["time"], timezone.utc)
            row.update({"date": row_date})

        df = pd.DataFrame(rows)
        df.set_index("date", inplace=True)

        return df

    async def get_tasks(self):
        pattern = "{}:{}:*".format(
            RedisPrefixes.NAMESPACE.value,
            RedisPrefixes.INFO.value)

        keys = await self._client.keys(pattern=pattern)

        return {key.decode().split(":")[-1] for key in keys}

    async def get_info(self, task):
        key = "{}:{}:{}".format(
            RedisPrefixes.NAMESPACE.value,
            RedisPrefixes.INFO.value,
            task)

        members = await self._client.zrange(key=key)
        rows = [json.loads(item) for item in members]
        rows.sort(key=lambda row: row["time"])

        return rows

    async def get_system_df(self, task):
        key = "{}:{}:{}".format(
            RedisPrefixes.NAMESPACE.value,
            RedisPrefixes.SYSTEM.value,
            task)

        return await self._get_zrange_df(key=key)

    async def get_packet_df(self, task):
        pattern = "{}:{}:*:{}".format(
            RedisPrefixes.NAMESPACE.value,
            RedisPrefixes.PACKET.value,
            task)

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

    async def extend_packet_df(self, df_packet, df_address=None):
        df_address = df_address if df_address else await self.get_address_df()
        df_address = df_address.reset_index().drop(columns=["iface", "date"])
        df_packet = df_packet.reset_index()

        df = pd.merge(
            df_packet, df_address,
            how="left", left_on="src", right_on="address")

        df = df.drop(columns=["address", "service_vip"]).rename(columns={
            "task": "src_task",
            "service": "src_service"
        })

        df = pd.merge(
            df, df_address,
            how="left", left_on="dst", right_on="address")

        df = df.drop(columns=["address", "service_vip"]).rename(columns={
            "task": "dst_task",
            "service": "dst_service"
        })

        na_cols = [
            col for col in ["src_task", "src_service", "dst_task", "dst_service"]
            if df[col].notna().any()
        ]

        if len(na_cols) > 0:
            _logger.warning((
                "Could not fill all columns on an extended "
                "packet DF (some columns contain NaN values): %s\n%s"
            ), na_cols, df)

        df.set_index(["date", "iface"], inplace=True)

        return df

    async def get_thing_df(self, task):
        key = "{}:{}:{}".format(
            RedisPrefixes.NAMESPACE.value,
            RedisPrefixes.THING.value,
            task)

        df = await self._get_zrange_df(key=key)
        df.set_index(["thing", "name", "verb"], append=True, inplace=True)

        return df

    async def get_address_df(self):
        tasks = await self.get_tasks()

        rows = [
            {
                "iface": iface,
                "address": iface_item["address"],
                "task": task,
                "service": info_item.get("env", {}).get(ENV_KEY_SERVICE_NAME),
                "service_vip": info_item.get("service_vip", None),
                "date": datetime.fromtimestamp(info_item["time"], timezone.utc)
            }
            for task in tasks
            for info_item in await self.get_info(task=task)
            for iface, iface_items in info_item.get("net", {}).items() if iface != _IFACE_LO
            for iface_item in iface_items if iface_item.get("family") == socket.AF_INET
        ]

        df = pd.DataFrame(rows)
        df.set_index(["date", "iface", "task"], inplace=True)

        return df
