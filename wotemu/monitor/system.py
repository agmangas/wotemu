import asyncio
import functools
import logging
import os
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


def _get_cpu_usage(cpu_constraint, cpu_count):
    cpu_percent = psutil.cpu_percent()
    ret = {"cpu_percent": cpu_percent}

    if cpu_constraint:
        ratio = cpu_count * cpu_percent * 1e-2
        constraint_ratio = float(ratio) / cpu_constraint
        constraint_percent = round(min(constraint_ratio, 1.0) * 1e2, 1)
        ret.update({"cpu_percent_constraint": constraint_percent})

    return ret


def _get_memory_usage():
    mem = psutil.virtual_memory()
    mem_mb = float(mem.total - mem.available) / (1024 * 1024)
    mem_percent = (float(mem.total - mem.available) / mem.total) * 1e2

    return {
        "mem_mb": round(mem_mb, 1),
        "mem_percent": round(mem_percent, 1)
    }


async def monitor_system(async_cb, sleep=5.0, group=2):
    cpu_constraint = _get_cpu_constraint()
    cpu_count = psutil.cpu_count()

    get_cpu = functools.partial(
        _get_cpu_usage,
        cpu_constraint=cpu_constraint,
        cpu_count=cpu_count)

    data = []

    try:
        # First CPU usage call to set reference:
        # https://psutil.readthedocs.io/en/latest/#psutil.cpu_percent
        get_cpu()
        await asyncio.sleep(sleep)

        while True:
            usage = {"time": time.time()}
            usage.update(get_cpu())
            usage.update(_get_memory_usage())
            data.append(usage)

            if not group or len(data) >= group:
                asyncio.ensure_future(async_cb(data.copy()))
                data.clear()

            await asyncio.sleep(sleep)
    except asyncio.CancelledError:
        _logger.debug("Cancelled system usage task")
