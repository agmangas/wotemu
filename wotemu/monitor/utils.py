import copy
import json
import logging
import socket
import time

import aioredis
import wotemu.config
from wotemu.enums import RedisPrefixes

_logger = logging.getLogger(__name__)
_state = {"redis": None}


async def _get_redis():
    try:
        assert await _state["redis"].ping()
    except:
        _logger.debug("Initializing module-level Redis pool")
        conf = wotemu.config.get_env_config()

        if not conf.redis_url:
            raise RuntimeError("Undefined Redis URL")

        redis_pool = await aioredis.create_redis(conf.redis_url)
        _state["redis"] = redis_pool

    return _state["redis"]


async def write_metric(key, data):
    redis_pool = await _get_redis()
    base_key = socket.getfqdn()

    full_key = "{}:{}:{}:{}".format(
        RedisPrefixes.NAMESPACE.value,
        RedisPrefixes.APP.value,
        base_key,
        key)

    now = time.time()
    data = copy.copy(data)
    data.update({"created_at": now})
    member = json.dumps(data)

    _logger.debug("ZADD %s: %s", full_key, member)

    await redis_pool.zadd(
        key=full_key,
        score=now,
        member=member)
