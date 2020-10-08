import asyncio
import json
import logging
import os
import time

import aioredis
import docker
import numpy
from wotemu.enums import RedisPrefixes
from wotemu.topology.compose import ENV_KEY_CPU_SPEED, ENV_KEY_NODE_ID
from wotemu.topology.cpu import get_cpu_core_scale, get_cpu_core_speed_poly
from wotemu.utils import get_current_container_id, ping_docker

_CPU_PERIOD = 100000
_KEY_CPU_PREFIX = "cpu"
_EXPIRE_SECS = 3600

_logger = logging.getLogger(__name__)


def _get_cpu_poly_key():
    node_id = os.environ.get(ENV_KEY_NODE_ID, None)

    if node_id is None:
        raise RuntimeError(f"Undefined ${ENV_KEY_NODE_ID}")

    return "{}:{}:{}".format(
        RedisPrefixes.NAMESPACE.value,
        RedisPrefixes.BENCHMARK.value,
        node_id)


def _local_cpu_poly():
    return get_cpu_core_speed_poly(cache=True)


async def _get_redis_poly(redis, key):
    _logger.debug("GET %s", key)
    val = await redis.get(key)

    if not val:
        return None

    coeffs = json.loads(val)

    return numpy.poly1d(coeffs) if coeffs else None


async def _set_redis_poly(redis, key, poly):
    val = json.dumps(poly.coeffs.tolist())
    _logger.debug("SET %s %s", key, val)
    await redis.set(key, val, expire=_EXPIRE_SECS)


async def _should_build_poly(redis, key):
    return not (await redis.get(key))


async def _lock_poly(redis, key):
    val = json.dumps(None)
    _logger.debug("SET %s %s", key, val)
    await redis.set(key, val, expire=_EXPIRE_SECS, exist=redis.SET_IF_NOT_EXIST)


async def _get_cpu_poly(redis_url, timeout=300, wait=2):
    key = _get_cpu_poly_key()

    if not key:
        raise ValueError("Undefined CPU speed poly Redis key")

    _logger.debug("Connecting to Redis: %s", redis_url)
    redis = await aioredis.create_redis_pool(redis_url)

    if (await _should_build_poly(redis, key)):
        _logger.info("Building CPU speed poly locally")
        await _lock_poly(redis, key)
        poly = _local_cpu_poly()
        await _set_redis_poly(redis, key, poly)
        return poly

    _logger.info("Waiting for CPU speed poly on Redis")

    ini = time.time()

    def _raise_timeout():
        if timeout is None:
            return

        if (time.time() - ini) >= timeout:
            raise Exception("Timeout waiting for Redis poly")

    while True:
        poly = await _get_redis_poly(redis, key)

        if poly:
            return poly
        else:
            await asyncio.sleep(wait)

        _raise_timeout()


def update_limits(conf, docker_url, speed, timeout, wait, local):
    ping_docker(docker_url=docker_url)

    cpu_poly = None

    if not local:
        _logger.debug((
            "Attempting to build the CPU speed poly "
            "in a distributed fashion using Redis as a "
            "central cache to avoid overloading the host "
            "with multiple parallel CPU speed benchmarks"
        ))

        try:
            loop = asyncio.get_event_loop()
            cpu_poly_fut = _get_cpu_poly(conf.redis_url, timeout, wait)
            cpu_poly = loop.run_until_complete(cpu_poly_fut)
        except Exception as ex:
            _logger.warning("Error getting CPU poly from Redis: %s", repr(ex))

    if not cpu_poly:
        _logger.info("Forced to build local CPU speed poly")
        cpu_poly = _local_cpu_poly()

    _logger.debug("Calculating the CPU scale to match target speed: %s", speed)
    speed_scale = get_cpu_core_scale(speed, core_poly=cpu_poly)

    _logger.debug("Getting current container to update CPU limits")
    cid = get_current_container_id()
    docker_client = docker.DockerClient(base_url=docker_url)
    curr_container = docker_client.containers.get(cid)

    update_kwargs = {
        "cpu_period": _CPU_PERIOD,
        "cpu_quota": int(_CPU_PERIOD * speed_scale)
    }

    _logger.info("Container update parameters: %s", update_kwargs)
    result = curr_container.update(**update_kwargs)

    _logger.log(
        logging.WARNING if result.get("Warnings", None) else logging.DEBUG,
        "Container update result: %s",
        result)
