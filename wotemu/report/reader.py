import functools
import json
import logging
import re
import socket
from datetime import datetime, timezone

import aioredis
import netaddr
import numpy as np
import pandas as pd
from wotemu.enums import RedisPrefixes
from wotemu.topology.compose import ENV_KEY_SERVICE_NAME

_IFACE_LO = "lo"
_DOCKER_TIME_REGEX = r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}).(\d+)Z$"
_DOCKER_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
_STATE_RUNNING = "running"

_logger = logging.getLogger(__name__)


def _parse_docker_time(val):
    match = re.match(_DOCKER_TIME_REGEX, val)

    if not match:
        return None

    dtime = datetime.strptime(match.group(1), _DOCKER_TIME_FORMAT)
    dtime = dtime.replace(tzinfo=timezone.utc)
    dtime = dtime.replace(microsecond=int(match.group(2)[:6]))

    return dtime


def _is_task_running(task_dict):
    return task_dict["DesiredState"] == _STATE_RUNNING


def _is_task_error(task_dict):
    is_running = _is_task_running(task_dict)

    exit_code = task_dict.\
        get("Status", {}).\
        get("ContainerStatus", {}).\
        get("ExitCode", 0)

    return not is_running and exit_code != 0


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

        if "date" in df:
            df.set_index("date", inplace=True)

        return df

    async def get_tasks(self):
        pattern = "{}:{}:*".format(
            RedisPrefixes.NAMESPACE.value,
            RedisPrefixes.INFO.value)

        keys = await self._client.keys(pattern=pattern)

        return {key.decode().split(":")[-1] for key in keys}

    async def get_info(self, task, latest=False):
        key = "{}:{}:{}".format(
            RedisPrefixes.NAMESPACE.value,
            RedisPrefixes.INFO.value,
            task)

        members = await self._client.zrange(key=key)
        rows = [json.loads(item) for item in members]
        rows.sort(key=lambda row: row["time"])

        if latest:
            return rows[-1] if len(rows) > 0 else None
        else:
            return rows

    async def get_info_map(self):
        task_keys = await self.get_tasks()

        ret = {
            task_key: await self.get_info(task_key, latest=True)
            for task_key in task_keys
        }

        return {task_key: info for task_key, info in ret.items() if info}

    async def get_compose_dict(self):
        key = "{}:{}".format(
            RedisPrefixes.NAMESPACE.value,
            RedisPrefixes.COMPOSE.value)

        members = await self._client.zrange(key=key, start=-1, stop=-1)

        if not members or not len(members):
            return None

        return json.loads(members[-1])

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
            "service": "src_service",
            "network": "src_network"
        })

        df = pd.merge(
            df, df_address,
            how="left", left_on="dst", right_on="address")

        df = df.drop(columns=["address"]).rename(columns={
            "task": "dst_task",
            "service": "dst_service",
            "network": "dst_network"
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

        df["network"] = df["src_network"].combine_first(df["dst_network"])

        df = df.drop(columns=[
            "src_vip_service",
            "dst_vip_service",
            "src_network",
            "dst_network"
        ])

        df.set_index(["date", "iface"], inplace=True)

        nan_series = df.isna().sum() / len(df)
        nan_series = nan_series[nan_series > 0]

        if len(nan_series) > 0:
            warn_cols = {"network", "len", "src", "dst", "proto", "transport"}
            is_warn = len(warn_cols.intersection(set(nan_series.index))) > 0

            _logger.log(
                logging.WARNING if is_warn else logging.DEBUG,
                "NaN ratio for extended packet DF (len: %s):\n%s",
                len(df), nan_series)

        return df

    async def get_thing_df(self, task):
        key = "{}:{}:{}".format(
            RedisPrefixes.NAMESPACE.value,
            RedisPrefixes.THING.value,
            task)

        df = await self._get_zrange_df(key=key)

        for col in ["thing", "name", "verb"]:
            if col in df:
                df.set_index([col], append=True, inplace=True)

        return df

    def _find_network(self, info_item, address):
        ip_addr = netaddr.IPAddress(address)
        networks_cidr = info_item.get("networks_cidr", {})

        try:
            return next(
                net_name
                for net_name, cidr_list in networks_cidr.items()
                for cidr in cidr_list
                if ip_addr in netaddr.IPNetwork(cidr))
        except StopIteration:
            return np.nan

    async def get_address_df(self, tasks=None):
        tasks = tasks if tasks else await self.get_tasks()

        rows = [
            {
                "date": datetime.fromtimestamp(info_item["time"], timezone.utc),
                "task": task,
                "service": info_item.get("env", {}).get(ENV_KEY_SERVICE_NAME),
                "iface": iface,
                "address": iface_item["address"],
                "network": self._find_network(info_item, iface_item["address"])
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

        return pd.concat(dfs.values(), ignore_index=True) if len(dfs) else None

    async def _get_task_key_map(self):
        task_keys = await self.get_tasks()

        task_infos = {
            task_key: await self.get_info(task_key)
            for task_key in task_keys
        }

        task_infos = {
            task_key: info_items[-1]
            for task_key, info_items in task_infos.items()
            if len(info_items) > 0
        }

        return {
            info_item["task_id"]: task_key
            for task_key, info_item in task_infos.items()
            if info_item.get("container_id")
        }

    async def get_snapshot_df(self):
        key = "{}:{}".format(
            RedisPrefixes.NAMESPACE.value,
            RedisPrefixes.SNAPSHOT.value)

        members = await self._client.zrange(key=key, start=-1, stop=-1, withscores=True)

        if len(members) == 0:
            _logger.warning("Could not find snapshot data")
            return None

        snapshot = json.loads(members[-1][0])
        snapshot_dtime = datetime.fromtimestamp(members[-1][1], timezone.utc)

        task_key_map = await self._get_task_key_map()

        rows = [
            {
                "desired_state": item["task"].get("DesiredState"),
                "is_running": _is_task_running(item["task"]),
                "is_error": _is_task_error(item["task"]),
                "task": task_key_map.get(task_id),
                "task_id": task_id,
                "node_id": item["task"].get("NodeID"),
                "service_id": item["task"].get("ServiceID"),
                "created_at": _parse_docker_time(item["task"].get("CreatedAt")),
                "updated_at": _parse_docker_time(item["task"].get("UpdatedAt")),
                "container_id": item["task"].get("Status", {}).get("ContainerStatus", {}).get("ContainerID"),
                "logs": item["logs"],
                "stopped_at": snapshot_dtime
            }
            for task_id, item in snapshot.items()
        ]

        df = pd.DataFrame(rows)

        return df
