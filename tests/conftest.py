import asyncio
import json
import logging
import os
import time
from collections import namedtuple

import aioredis
import docker
import pytest
from wotemu.report.reader import ReportDataRedisReader

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
_REDIS_DATA_FILE = "./redis_data.json"

RedisService = namedtuple(
    "RedisService",
    ["url", "container"])

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
        return RedisService(url=redis_url, container=None)

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


def _insert_zset(tr, item):
    assert item["type"] == "zset"

    for value_item in item["value"]:
        tr.zadd(
            key=item["key"],
            score=value_item[1],
            member=value_item[0])


@pytest.fixture
async def redis_loaded(redis):
    current_dir = os.path.dirname(os.path.realpath(__file__))
    data_file = os.path.join(current_dir, _REDIS_DATA_FILE)

    with open(data_file, "r") as fh:
        data = json.loads(fh.read())

    tr = redis.multi_exec()

    for item in data:
        _logger.debug(
            "Loading '%s' (type: %s) (size: %s)",
            item.get("key"), item.get("type"), len(item.get("value", [])))

        if item["type"] == "zset":
            _insert_zset(tr, item)

    await tr.execute()

    return redis


@pytest.fixture
async def redis_reader(redis_loaded):
    host, port = redis_loaded.connection.address
    db = redis_loaded.connection.db
    redis_url = f"redis://{host}:{port}/{db}"
    reader = ReportDataRedisReader(redis_url=redis_url)
    await reader.connect()
    yield reader
    await reader.close()


@pytest.fixture
def redis_test_data():
    current_dir = os.path.dirname(os.path.realpath(__file__))
    data_file = os.path.join(current_dir, _REDIS_DATA_FILE)

    with open(data_file, "r") as fh:
        data = json.loads(fh.read())
        return RedisTestData(data)


class RedisTestData:
    def __init__(self, data):
        self._data = data

    def get_num_tasks(self):
        return len(set(
            item["key"]
            for item in self._data
            if item["key"].startswith("wotemu:info:")))

    def _next_task_with_data(self, redis_key):
        prefix = "wotemu:{}:".format(redis_key)

        return next(
            item["key"].split(":")[-1]
            for item in self._data
            if item["key"].startswith(prefix))

    def get_task_with_system_data(self):
        return self._next_task_with_data(redis_key="system")

    def get_task_with_packet_data(self):
        return self._next_task_with_data(redis_key="packet")

    def get_task_with_thing_data(self):
        return self._next_task_with_data(redis_key="thing")
