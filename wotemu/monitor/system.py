import asyncio
import functools
import logging
import os
import platform
import socket
import time

import psutil

_PATH_PERIOD = "/sys/fs/cgroup/cpu/cpu.cfs_period_us"
_PATH_QUOTA = "/sys/fs/cgroup/cpu/cpu.cfs_quota_us"

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


def get_node_info():
    net_addrs = {
        key: [item._asdict() for item in val]
        for key, val in psutil.net_if_addrs().items()
    }

    disks = [
        item._asdict()
        for item in psutil.disk_partitions(all=False)
    ]

    return {
        "cpu_count": psutil.cpu_count(),
        "mem_total": psutil.virtual_memory().total,
        "net": net_addrs,
        "disks": disks,
        "python_version": platform.python_version(),
        "uname": platform.uname()._asdict()
    }
