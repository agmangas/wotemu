import asyncio
import logging
import sys
import time

import aioredis
from hbmqtt.client import MQTTClient

from wotemu.utils import ping_docker

_logger = logging.getLogger(__name__)


async def _ping_redis(redis_url):
    try:
        redis = await aioredis.create_redis_pool(redis_url)
        assert redis.ping()
        return True
    except Exception as ex:
        _logger.debug("Redis unavailable: %s", ex)
        return False
    finally:
        try:
            redis.close()
            await redis.wait_closed()
        except:
            pass


def _ping_docker(docker_url):
    try:
        ping_docker(docker_url)
        return True
    except Exception as ex:
        _logger.debug("Docker API unavailable: %s", ex)
        return False


async def _wait_base(redis_url, docker_url, sleep):
    while not (await _ping_redis(redis_url)):
        await asyncio.sleep(sleep)

    while not _ping_docker(docker_url):
        await asyncio.sleep(sleep)


def _wait_base_timeout(redis_url, docker_url, sleep, timeout):
    loop = asyncio.get_event_loop()
    base_aw = _wait_base(redis_url, docker_url, sleep)
    loop.run_until_complete(asyncio.wait_for(base_aw, timeout=timeout))


async def _ping_broker(broker_url):
    try:
        client = MQTTClient()
        await client.connect(broker_url)
        return True
    except Exception as ex:
        _logger.debug("MQTT broker unavailable: %s", ex)
        return False
    finally:
        try:
            await client.disconnect()
        except:
            pass


async def _wait_broker(broker_url, sleep):
    while not (await _ping_broker(broker_url)):
        await asyncio.sleep(sleep)


def _wait_broker_timeout(broker_url, sleep, timeout):
    loop = asyncio.get_event_loop()
    broker_aw = _wait_broker(broker_url, sleep)
    loop.run_until_complete(asyncio.wait_for(broker_aw, timeout=timeout))


def wait_services(conf, sleep, timeout, waiter_base, waiter_mqtt):
    try:
        if waiter_base:
            _logger.info(
                "Waiting for Docker API (%s) and Redis (%s)",
                conf.docker_proxy_url,
                conf.redis_url)

            _wait_base_timeout(
                redis_url=conf.redis_url,
                docker_url=conf.docker_proxy_url,
                sleep=sleep,
                timeout=timeout)

        if waiter_mqtt and conf.mqtt_url:
            _logger.info("Waiting for MQTT broker (%s)", conf.mqtt_url)

            _wait_broker_timeout(
                broker_url=conf.mqtt_url,
                sleep=sleep,
                timeout=timeout)
        elif waiter_mqtt and not conf.mqtt_url:
            _logger.info("No MQTT broker configuration found in environment")
    except Exception:
        _logger.error("Error waiting for services", exc_info=True)
        sys.exit(1)
