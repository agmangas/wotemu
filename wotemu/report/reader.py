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

    async def get_packet_df(self, task, extended=False):
        pattern = "{}:{}:*:{}".format(
            RedisPrefixes.NAMESPACE.value,
            RedisPrefixes.PACKET.value,
            task)

        packet_keys = await self._client.keys(pattern=pattern)

        if len(packet_keys) == 0:
            _logger.debug(
                "No packet keys found for task '%s': Undefined packet DF", task)

            return None

        dfs = []

        for key in packet_keys:
            iface = key.decode().split(":")[2]
            df_iface = await self._get_zrange_df(key=key)
            df_iface["iface"] = iface
            df_iface.set_index(["iface"], append=True, inplace=True)
            dfs.append(df_iface)

        df = pd.concat(dfs)
        df.sort_index(inplace=True)

        if extended:
            df = await self.extend_packet_df(df_packet=df)

        return df

    async def extend_packet_df(self, df_packet, df_address=None, df_vip=None):
        df_address = df_address if df_address else await self.get_address_df()
        df_address = df_address.reset_index().drop(columns=["iface", "date"])

        df_vip = df_vip if df_vip else await self.get_service_vip_df()
        df_vip = df_vip.reset_index().drop(columns=["date", "task"])

        df_packet = df_packet.reset_index()

        df = pd.merge(
            df_packet, df_address,
            how="left", left_on="src", right_on="address")

        df = df.drop(columns=["address"]).rename(columns={
            "task": "src_task",
            "service": "src_service"
        })

        df = pd.merge(
            df, df_address,
            how="left", left_on="dst", right_on="address")

        df = df.drop(columns=["address"]).rename(columns={
            "task": "dst_task",
            "service": "dst_service"
        })

        df = pd.merge(
            df, df_vip,
            how="left", left_on="src", right_on="vip")

        df = df.drop(columns=["vip", "network"]).rename(columns={
            "service": "src_vip_service"
        })

        df = pd.merge(
            df, df_vip,
            how="left", left_on="dst", right_on="vip")

        df = df.drop(columns=["vip", "network"]).rename(columns={
            "service": "dst_vip_service"
        })

        df["src_service"] = df["src_service"].fillna(
            value=df["src_vip_service"])

        df["dst_service"] = df["dst_service"].fillna(
            value=df["dst_vip_service"])

        df = df.drop(columns=["src_vip_service", "dst_vip_service"])
        df.set_index(["date", "iface"], inplace=True)

        _logger.debug(
            "NaN ratio for extended packet DF (len: %s):\n%s",
            len(df), df.isna().sum() / len(df))

        return df

    async def get_thing_df(self, task):
        key = "{}:{}:{}".format(
            RedisPrefixes.NAMESPACE.value,
            RedisPrefixes.THING.value,
            task)

        df = await self._get_zrange_df(key=key)
        df.set_index(["thing", "name", "verb"], append=True, inplace=True)

        return df

    async def get_address_df(self, tasks=None):
        tasks = tasks if tasks else await self.get_tasks()

        rows = [
            {
                "date": datetime.fromtimestamp(info_item["time"], timezone.utc),
                "task": task,
                "service": info_item.get("env", {}).get(ENV_KEY_SERVICE_NAME),
                "iface": iface,
                "address": iface_item["address"]
            }
            for task in tasks
            for info_item in await self.get_info(task=task)
            for iface, iface_items in info_item.get("net", {}).items() if iface != _IFACE_LO
            for iface_item in iface_items if iface_item.get("family") == socket.AF_INET
        ]

        df = pd.DataFrame(rows)
        df.set_index(["date", "task", "iface"], inplace=True)

        return df

    async def get_service_vip_df(self, tasks=None):
        tasks = tasks if tasks else await self.get_tasks()

        rows = [
            {
                "date": datetime.fromtimestamp(info_item["time"], timezone.utc),
                "task": task,
                "service": info_item.get("env", {}).get(ENV_KEY_SERVICE_NAME),
                "network": net_name,
                "vip": vip
            }
            for task in tasks
            for info_item in await self.get_info(task=task)
            for net_name, vip in info_item.get("service_vips", {}).items()
        ]

        df = pd.DataFrame(rows)
        df.set_index(["date", "task", "network"], inplace=True)

        return df

    async def get_service_traffic_df(self, tasks=None, inbound=True):
        tasks = tasks if tasks else await self.get_tasks()

        col_task = "src_task" if inbound else "dst_task"
        col_service = "dst_service" if inbound else "src_service"

        dfs = {
            task: await self.get_packet_df(task, extended=True)
            for task in tasks
        }

        dfs = {
            task: df[(df[col_task] == task) & df[col_service].notna()]
            for task, df in dfs.items()
            if df is not None
        }

        dfs = {
            task: df.groupby(col_service)["len"].sum().to_frame()
            for task, df in dfs.items()
        }

        for task, df in dfs.items():
            df.reset_index(inplace=True)
            df[col_task] = task

        return pd.concat(dfs.values())
