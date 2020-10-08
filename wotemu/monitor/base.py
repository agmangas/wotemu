import asyncio
import functools
import json
import logging
import pprint
import socket
import time

import aioredis
import wotemu.config
from wotemu.enums import RedisPrefixes
from wotemu.monitor.packet import monitor_packets
from wotemu.monitor.system import get_node_info, monitor_system

_logger = logging.getLogger(__name__)


class NodeMonitor:
    def __init__(
            self, key=None, redis_url=None, packet_ifaces=None,
            packet_kwargs=None, system_kwargs=None):
        conf = wotemu.config.get_env_config()
        self._conf = conf
        self._key = key if key else socket.getfqdn()
        self._redis_url = redis_url if redis_url else conf.redis_url
        self._redis = None
        self._packet_ifaces = packet_ifaces
        self._packet_kwargs = packet_kwargs if packet_kwargs else {}
        self._system_kwargs = system_kwargs if system_kwargs else {}
        self._task_system = None
        self._tasks_packet = None

    @property
    def is_running(self):
        return self._task_system or self._tasks_packet

    async def _redis_open(self):
        if self._redis:
            return

        self._redis = await aioredis.create_redis_pool(self._redis_url)
        _logger.debug("Opened Redis connection to: %s", self._redis_url)

    async def _redis_close(self):
        if not self._redis:
            return

        self._redis.close()
        await self._redis.wait_closed()
        self._redis = None
        _logger.debug("Closed Redis connection")

    async def _redis_callback(self, items, key):
        _logger.debug("ZADD (%s items): %s", len(items), key)

        tr = self._redis.multi_exec()

        for item in items:
            score = item.get("time", time.time())
            member = json.dumps(item)
            tr.zadd(key=key, score=score, member=member)

        exec_res = await tr.execute()

        if not all(exec_res):
            _logger.warning("Error in Redis MULTI ZADD: %s", exec_res)

    async def _create_system_task(self):
        assert not self._task_system

        key = "{}:{}:{}".format(
            RedisPrefixes.NAMESPACE.value,
            RedisPrefixes.SYSTEM.value,
            self._key)

        async_cb = functools.partial(self._redis_callback, key=key)

        system_awaitable = monitor_system(
            async_cb=async_cb,
            **self._system_kwargs)

        self._task_system = asyncio.ensure_future(system_awaitable)

    async def _create_packet_tasks(self):
        assert not self._tasks_packet

        if not self._packet_ifaces or not len(self._packet_ifaces):
            return

        packet_awaitables = []

        for iface in self._packet_ifaces:
            key = "{}:{}:{}:{}".format(
                RedisPrefixes.NAMESPACE.value,
                RedisPrefixes.PACKET.value,
                iface,
                self._key)

            async_cb = functools.partial(self._redis_callback, key=key)

            packet_awaitables.append(monitor_packets(
                conf=self._conf,
                interface=iface,
                async_cb=async_cb))

        self._tasks_packet = [
            asyncio.ensure_future(item)
            for item in packet_awaitables
        ]

    async def _stop_system_task(self):
        if not self._task_system:
            return

        self._task_system.cancel()
        await self._task_system
        self._task_system = None

    async def _stop_packet_tasks(self):
        if not self._tasks_packet:
            return

        [task.cancel() for task in self._tasks_packet]
        await asyncio.gather(*self._tasks_packet)
        self._tasks_packet = None

    async def _write_node_info(self):
        assert self._redis

        node_info = get_node_info()
        tstamp = time.time()
        node_info.update({"time": tstamp})
        member = json.dumps(node_info)

        key = "{}:{}:{}".format(
            RedisPrefixes.NAMESPACE.value,
            RedisPrefixes.INFO.value,
            self._key)

        _logger.debug(
            "Writing node info - ZADD %s:\n%s",
            key, pprint.pformat(node_info))

        await self._redis.zadd(key=key, score=tstamp, member=member)

    async def start(self):
        if self.is_running:
            raise RuntimeError("Already running")

        _logger.debug("Starting node monitor")

        await self._redis_open()
        await self._write_node_info()
        await self._create_system_task()
        await self._create_packet_tasks()

    async def stop(self):
        _logger.debug("Stopping node monitor")

        await self._stop_system_task()
        await self._stop_packet_tasks()
        await self._redis_close()

        self._task_system = None
        self._tasks_packet = None
