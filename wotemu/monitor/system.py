import asyncio
import functools
import json
import logging
import os
import platform
import pprint
import re
import socket
import time

import docker
import psutil
import sh
import wotemu.config
from wotemu.topology.compose import ENV_KEY_SERVICE_NAME
from wotemu.utils import (cgget, get_current_container_id, get_current_task,
                          get_task_networks)

_CPU_USAGE = "cpuacct.usage"
_CPU_PERIOD = "cpu.cfs_period_us"
_CPU_QUOTA = "cpu.cfs_quota_us"
_MEM_LIMIT = "memory.limit_in_bytes"
_MEM_USAGE = "memory.usage_in_bytes"
_NSLOOKUP_REGEX = r"Name:\s.+\..+\nAddress:\s(.+)"

_logger = logging.getLogger(__name__)

_times = {
    "system": None,
    "cgroup": None
}


class CggetError(RuntimeError):
    def __init__(self, key):
        msg = (
            "Could not read cgroup parameter '{}'"
            "using the cgget command. Please make "
            "sure that cgget is installed on your system."
        ).format(key)

        super().__init__(msg)


def _get_cpu_nanos_system():
    cput = psutil.cpu_times()
    return (cput.user + cput.system + cput.idle) * 1e9


def _get_cpu_nanos():
    usage = cgget(_CPU_USAGE)

    if usage is None:
        raise CggetError(_CPU_USAGE)

    return usage


def _is_times_state_empty():
    return _times["system"] is None or _times["cgroup"] is None


def _update_times_state():
    _times.update({
        "system": _get_cpu_nanos_system(),
        "cgroup": _get_cpu_nanos()
    })


def _get_cpu_percent():
    if _is_times_state_empty():
        _update_times_state()
        return None

    curr_cpu = _get_cpu_nanos()
    curr_sys = _get_cpu_nanos_system()

    delta_cpu = float(curr_cpu - _times["cgroup"])
    delta_sys = float(curr_sys - _times["system"])

    _times.update({
        "system": curr_sys,
        "cgroup": curr_cpu
    })

    if delta_cpu > 0 and delta_sys > 0:
        return (delta_cpu / delta_sys) * psutil.cpu_count() * 100.0
    else:
        return 0.0


def _get_cpu_constraint():
    period = cgget(_CPU_PERIOD)

    if period is None:
        raise CggetError(_CPU_PERIOD)

    quota = cgget(_CPU_QUOTA)

    if quota is None:
        raise CggetError(_CPU_QUOTA)

    return (float(quota) / float(period)) if quota > 0 else None


def _get_cpu():
    cpu_percent = _get_cpu_percent()

    if cpu_percent is None:
        return None

    ret = {"cpu_percent": round(cpu_percent, 1)}

    cpu_constraint = _get_cpu_constraint()

    if cpu_constraint:
        constraint_ratio = (cpu_percent * 1e-2) / cpu_constraint
        constraint_percent = round(constraint_ratio * 1e2, 1)
        ret.update({"cpu_percent_constraint": constraint_percent})

    return ret


def _get_memory_limit():
    limit_bytes = cgget(_MEM_LIMIT)
    total_bytes_system = psutil.virtual_memory().total

    if limit_bytes and limit_bytes < total_bytes_system:
        return limit_bytes
    else:
        return total_bytes_system


def _get_memory():
    mem_usage = cgget(_MEM_USAGE)

    if mem_usage is None:
        raise CggetError(_MEM_USAGE)

    mem_limit = _get_memory_limit()
    mem_usage_mb = mem_usage / (1024.0 ** 2)
    mem_limit_mb = mem_limit / (1024.0 ** 2)
    mem_percent = (mem_usage_mb / mem_limit_mb) * 100.0

    return {
        "mem_mb": round(mem_usage_mb, 2),
        "mem_percent": round(mem_percent, 1)
    }


def _read_system(data, read_funcs):
    datum = {"time": time.time()}

    read_results = []

    for func in read_funcs:
        try:
            read_results.append(func())
        except Exception as ex:
            _logger.warning("System monitor error: %s", repr(ex))

    [
        datum.update(item)
        for item in read_results if item
    ]

    data.append(datum)


async def _invoke_callback(data, group_size, async_cb):
    if not group_size or len(data) >= group_size:
        await async_cb(data)
        data.clear()


async def monitor_system(async_cb, sleep=5.0, group_size=2):
    data = []

    read_system = functools.partial(
        _read_system,
        data=data,
        read_funcs=(_get_cpu, _get_memory))

    invoke_callback = functools.partial(
        _invoke_callback,
        data=data,
        group_size=group_size,
        async_cb=async_cb)

    try:
        _get_cpu()
        await asyncio.sleep(sleep)

        while True:
            read_system()
            await invoke_callback()
            await asyncio.sleep(sleep)
    except asyncio.CancelledError:
        _logger.debug("Cancelled system usage task")


def _get_service_vips():
    service_name = os.environ[ENV_KEY_SERVICE_NAME]
    conf = wotemu.config.get_env_config()
    docker_url = conf.docker_proxy_url
    curr_task = get_current_task(docker_url=docker_url)
    net_ids = get_task_networks(docker_url=docker_url, task=curr_task)
    docker_api_client = docker.APIClient(base_url=docker_url)

    net_names = [
        docker_api_client.inspect_network(nid).get("Name")
        for nid in net_ids
    ]

    nslookup = sh.Command("nslookup")

    nslookup_results = {
        net_name: nslookup(f"{service_name}.{net_name}")
        for net_name in net_names
    }

    _logger.debug(
        "VIP nslookup results for service '%s':\n%s",
        service_name,
        pprint.pformat(nslookup_results))

    re_results = {
        net_name: re.search(_NSLOOKUP_REGEX, str(res))
        for net_name, res in nslookup_results.items()
    }

    assert all(re_results.values())
    assert all(len(res.groups()) == 1 for res in re_results.values())

    vips = {
        net_name: res.groups()[0]
        for net_name, res in re_results.items()
    }

    _logger.debug(
        "Service '%s' VIPs obtained from nslookup: %s",
        service_name, vips)

    return vips


def _get_task_id():
    conf = wotemu.config.get_env_config()
    docker_url = conf.docker_proxy_url
    curr_task = get_current_task(docker_url=docker_url)
    return curr_task["ID"]


def get_node_info():
    net_addrs = {
        key: [item._asdict() for item in val]
        for key, val in psutil.net_if_addrs().items()
    }

    procs = {
        proc.pid: proc.info
        for proc in psutil.process_iter(["name", "username"])
    }

    info = {
        "cpu_count": psutil.cpu_count(),
        "mem_total": psutil.virtual_memory().total,
        "net": net_addrs,
        "python_version": platform.python_version(),
        "uname": platform.uname()._asdict(),
        "process": procs,
        "boot_time": psutil.boot_time(),
        "env": dict(os.environ),
        "hostname": socket.gethostname()
    }

    try:
        info.update({"service_vips": _get_service_vips()})
    except:
        _logger.warning("Error reading service VIPs", exc_info=True)

    try:
        info.update({"container_id": get_current_container_id()})
    except:
        _logger.warning("Error reading container ID", exc_info=True)

    try:
        info.update({"task_id": _get_task_id()})
    except:
        _logger.warning("Error reading task ID", exc_info=True)

    return json.loads(json.dumps(info))
