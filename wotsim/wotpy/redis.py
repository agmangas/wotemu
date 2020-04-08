import json
import logging
import os

import aioredis

_ENV_REDIS_URL = "REDIS_URL"

_logger = logging.getLogger(__name__)


async def redis_from_env():
    redis_url = os.getenv(_ENV_REDIS_URL, None)

    if not redis_url:
        raise Exception("Undefined Redis URL (${})".format(_ENV_REDIS_URL))

    return await aioredis.create_redis_pool(redis_url)


async def redis_thing_callback(data, client=None):
    try:
        redis = None
        redis = client if client else await redis_from_env()
        await redis.zadd(key=data["host"], score=data["time"], member=json.dumps(data))
    except Exception as ex:
        _logger.warning("Error in Redis callback: %s", ex)
    finally:
        if client is None and redis:
            redis.close()
            await redis.wait_closed()
