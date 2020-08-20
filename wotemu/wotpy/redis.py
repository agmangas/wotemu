import json
import logging
import os

import aioredis

import wotemu.config

PREFIX_THING = "thing"
KEY_SEPARATOR = ":"

_logger = logging.getLogger(__name__)


async def redis_from_env():
    env_config = wotemu.config.get_env_config()

    if not env_config.redis_url:
        raise Exception("Undefined Redis URL")

    return await aioredis.create_redis_pool(env_config.redis_url)


async def redis_thing_callback(data, client=None):
    try:
        redis = None
        redis = client if client else await redis_from_env()
        key = "".join([PREFIX_THING, KEY_SEPARATOR, data["host"]])
        score = data["time"]
        member = json.dumps(data)
        await redis.zadd(key=key, score=score, member=member)
    except Exception as ex:
        _logger.warning("Error in Redis callback: %s", ex)
    finally:
        if client is None and redis:
            redis.close()
            await redis.wait_closed()
