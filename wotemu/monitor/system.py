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
from wotemu.utils import get_current_task, get_task_networks

_PATH_PERIOD = "/sys/fs/cgroup/cpu/cpu.cfs_period_us"
_PATH_QUOTA = "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"
_NSLOOKUP_REGEX = r"Name:\s.+\..+\nAddress:\s(.+)"

_logger = logging.getLogger(__name__)


def _get_cpu_constraint():
    try:
        with open(_PATH_PERIOD, "r") as fh:
            period = float(fh.read().strip())

        with open(_PATH_QUOTA, "r") as fh:
            quota = float(fh.read().strip())

        return (quota / period) if quota > 0 else None
    except Exception as ex:
        _logger.debug("Error reading container CPU constraint: %s", ex)
        return None


def _get_cpu(cpu_constraint, cpu_count):
    cpu_percent = psutil.cpu_percent()
    ret = {"cpu_percent": cpu_percent}

    if cpu_constraint:
        ratio = cpu_count * cpu_percent * 1e-2
        constraint_ratio = float(ratio) / cpu_constraint
        constraint_percent = round(min(constraint_ratio, 1.0) * 1e2, 1)
        ret.update({"cpu_percent_constraint": constraint_percent})

    return ret


def _get_memory():
    mem = psutil.virtual_memory()
    mem_mb = float(mem.total - mem.available) / (1024 * 1024)
    mem_percent = (float(mem.total - mem.available) / mem.total) * 1e2

    return {
        "mem_mb": round(mem_mb, 1),
        "mem_percent": round(mem_percent, 1)
    }


def _read_system(data, read_funcs):
    datum = {"time": time.time()}

    for func in read_funcs:
        datum.update(func())

    data.append(datum)


async def _invoke_callback(data, group_size, async_cb):
    if not group_size or len(data) >= group_size:
        await async_cb(data)
        data.clear()


async def monitor_system(async_cb, sleep=5.0, group_size=2):
    cpu_constraint = _get_cpu_constraint()
    cpu_count = psutil.cpu_count()

    _logger.debug("CPU constraint ratio: %s", cpu_constraint)
    _logger.debug("CPU count: %s", cpu_count)

    get_cpu = functools.partial(
        _get_cpu,
        cpu_constraint=cpu_constraint,
        cpu_count=cpu_count)

    data = []

    read_system = functools.partial(
        _read_system,
        data=data,
        read_funcs=(get_cpu, _get_memory))

    invoke_callback = functools.partial(
        _invoke_callback,
        data=data,
        group_size=group_size,
        async_cb=async_cb)

    try:
        # First CPU usage call to set reference:
        # https://psutil.readthedocs.io/en/latest/#psutil.cpu_percent
        get_cpu()
        await asyncio.sleep(sleep)

        while True:
            read_system()
            await invoke_callback()
            await asyncio.sleep(sleep)
    except asyncio.CancelledError:
        _logger.debug("Cancelled system usage task")


def _get_service_vips():
    try:
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
    except:
        _logger.warning("Error reading service VIPs", exc_info=True)
        return None


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
        "env": dict(os.environ)
    }

    service_vips = _get_service_vips()

    if service_vips:
        info.update({"service_vips": service_vips})

    return json.loads(json.dumps(info))
