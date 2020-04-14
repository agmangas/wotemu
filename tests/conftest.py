import asyncio
import logging
import os
import time
from collections import namedtuple

import aioredis
import docker
import pytest

TD_EXAMPLE = {
    "id": "urn:org:fundacionctic:thing:testthing",
    "name": "Test Thing",
    "properties": {
        "testProp": {
            "description": "Test property",
            "type": "number",
            "readOnly": False,
            "observable": True
        }
    }
}

_ENV_REDIS_TEST = "TEST_REDIS_URL"
_DOCKER_REDIS_IMAGE = "redis:5"
_DOCKER_REDIS_PORT = "6379/tcp"

RedisService = namedtuple(
    "RedisService",
    ["url", "container"],
    defaults=(None,))

_logger = logging.getLogger(__name__)


def start_redis_container():
    client = docker.from_env()
    assert client.ping(), "Error on Docker ping"

    _logger.debug("Pulling image: %s", _DOCKER_REDIS_IMAGE)

    client.images.pull(_DOCKER_REDIS_IMAGE)

    container = client.containers.run(
        image=_DOCKER_REDIS_IMAGE,
        detach=True,
        ports={_DOCKER_REDIS_PORT: None})

    _logger.debug("Created Redis container: %s", container.name)

    inspect_data = client.api.inspect_container(container.id)
    port = inspect_data["NetworkSettings"]["Ports"][_DOCKER_REDIS_PORT][0]["HostPort"]
    url = "redis://localhost:{}".format(port)

    _logger.debug("Redis container URL: %s", url)

    return RedisService(container=container, url=url)


def get_redis_service():
    redis_url = os.getenv(_ENV_REDIS_TEST, None)

    if redis_url:
        _logger.debug("Using Redis from environment: %s", redis_url)
        return RedisService(url=redis_url)

    _logger.warning(
        "Undefined Redis URL ($%s): Creating volatile Docker container",
        _ENV_REDIS_TEST)

    return start_redis_container()


async def wait_redis(redis_service, timeout=10.0):
    ini = time.time()

    while True:
        try:
            _logger.debug("Waiting for Redis service")
            redis = await aioredis.create_redis_pool(redis_service.url)
            assert await redis.ping()
            _logger.debug("Redis service ping OK")
            break
        except Exception as ex:
            _logger.debug("Error on Redis ping: %s", ex)

            if (time.time() - ini) > timeout:
                msg = "Redis service timeout ({} s)".format(timeout)
                _logger.warning(msg)
                raise Exception(msg)
        finally:
            try:
                redis.close()
                await redis.wait_closed()
            except:
                pass


@pytest.fixture
async def redis():
    try:
        redis_service = get_redis_service()
        await wait_redis(redis_service)
        redis = await aioredis.create_redis_pool(redis_service.url)
        await redis.flushdb()
        yield redis
        await redis.flushdb()
        redis.close()
        await redis.wait_closed()
    except Exception as ex:
        msg = "Error initiliazing Redis fixture: {}".format(ex)
        _logger.warning(msg)
        pytest.skip(msg)
    finally:
        try:
            redis_service.container.remove(force=True, v=True)
        except:
            pass
