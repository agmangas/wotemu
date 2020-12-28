import asyncio
import functools
import importlib
import inspect
import logging
import os
import pprint
import re
import signal
import sys
import tempfile

import aioredis
import coloredlogs
import tornado.httpclient
import wotemu.config
import wotemu.wotpy.redis
import wotemu.wotpy.wot
from wotemu.enums import BUILTIN_APPS_MODULES, BuiltinApps
from wotemu.monitor.base import NodeMonitor
from wotemu.utils import (get_current_task, get_network_gateway_task,
                          get_output_iface_for_task, get_task_networks,
                          import_func)

_TIMEOUT = 15
_HTTP_REGEX = r"^https?:\/\/.*"

_logger = logging.getLogger(__name__)


def _fetch_app_file(url):
    _logger.info("Fetching WoT app from: %s", url)

    http_client = tornado.httpclient.HTTPClient()
    res = http_client.fetch(url)
    _os_fh, abs_path = tempfile.mkstemp(suffix=".py")

    _logger.debug("Writing WoT app to: %s", abs_path)

    with open(abs_path, "wb") as fh:
        fh.write(res.body)

    return abs_path


def _remove_tempfile(fpath):
    if not fpath or not fpath.startswith(tempfile.gettempdir()):
        return

    try:
        _logger.debug("Removing tempfile: %s", fpath)
        os.remove(fpath)
    except:
        _logger.warning("Error removing tempfile", exc_info=True)


def _is_builtin_app(app_id):
    try:
        assert app_id in BuiltinApps
        return True
    except:
        pass

    return app_id in [item.value for item in BuiltinApps]


def _import_builtin_app_func(app_id, func_name):
    bapp = next(item for item in BuiltinApps if item.value == app_id)
    mod_name = BUILTIN_APPS_MODULES[bapp]
    mod_import = importlib.import_module(mod_name)
    mod_dir = dir(mod_import)

    _logger.info("Imported: %s", mod_import)
    _logger.debug("dir(%s): %s", mod_import, mod_dir)

    if func_name not in mod_dir:
        raise Exception("Builtin app module {} does not contain {}".format(
            mod_import, func_name))

    return getattr(mod_import, func_name)


def _import_app_func(module_path, func_name):
    _logger.debug("Attempting to import from: %s", module_path)

    if _is_builtin_app(app_id=module_path):
        return _import_builtin_app_func(app_id=module_path, func_name=func_name)

    if re.match(_HTTP_REGEX, module_path):
        module_path = _fetch_app_file(module_path)

    try:
        app_func = import_func(module_path=module_path, func_name=func_name)
        app_func_sig = inspect.signature(app_func)
        _logger.debug("Function (%s) signature: %s", app_func, app_func_sig)
        return app_func
    finally:
        _remove_tempfile(module_path)


def _build_thing_cb(redis_url, loop):
    async def dummy_cb(*args, **kwargs):
        pass

    if not redis_url:
        return dummy_cb, None

    _logger.debug("Creating Redis pool with URL: %s", redis_url)

    redis_pool = loop.run_until_complete(
        aioredis.create_redis_pool(redis_url))

    redis_cb = functools.partial(
        wotemu.wotpy.redis.redis_thing_callback,
        client=redis_pool)

    return redis_cb, redis_pool


def _exception_handler(loop, context):
    level = logging.ERROR if loop.is_running() else logging.DEBUG
    _logger.log(level, "Exception in loop:\n%s", pprint.pformat(context))


async def _start_servient(wot):
    try:
        _logger.debug("Starting Servient: %s", wot.servient)
        await wot.servient.start()
    except Exception:
        _logger.error("Error in Servient startup", exc_info=True)
        sys.exit(1)


async def _stop_servient(wot):
    try:
        _logger.debug("Shutting down Servient: %s", wot.servient)
        await wot.servient.shutdown()
    except Exception:
        _logger.warning("Error in Servient shutdown", exc_info=True)


async def _stop_redis(redis_pool):
    if not redis_pool:
        return

    try:
        _logger.debug("Closing Redis")
        redis_pool.close()
        await redis_pool.wait_closed()
    except Exception:
        _logger.warning("Error in Redis shutdown", exc_info=True)


async def _stop(loop, app_task, wot, redis_pool, monitor, lock):
    if lock.locked():
        _logger.debug("Another stop task is already in progress")
        return

    async with lock:
        try:
            _logger.info("Cancelling WoT app task: %s", app_task)
            app_task.cancel()
            await asyncio.wait_for(app_task, _TIMEOUT)
        except Exception:
            _logger.warning("Error during WoT app cancelation", exc_info=True)

        await _stop_servient(wot=wot)

        if monitor:
            await monitor.stop()

        await _stop_redis(redis_pool=redis_pool)

        _logger.debug("Stopping loop")
        loop.stop()


def _app_done_cb(fut, stop, exit_status):
    if fut.cancelled() or not fut.exception():
        return

    err = repr(fut.exception())
    _logger.error("WoT app error: %s", err)
    exit_status["code"] = 1
    asyncio.ensure_future(stop())


def _get_monitor_ifaces(docker_url):
    curr_task = get_current_task(docker_url=docker_url)

    wotemu_network_ids = get_task_networks(
        docker_url=docker_url,
        task=curr_task)

    gw_tasks = [
        get_network_gateway_task(
            docker_url=docker_url,
            network_id=net_id)
        for net_id in wotemu_network_ids
    ]

    return [
        get_output_iface_for_task(gw_task)[0]
        for gw_task in gw_tasks
    ]


def run_app(
        conf, path, func, func_param, hostname,
        enable_http, enable_mqtt, enable_coap, enable_ws, disable_monitor):
    if not enable_http and not enable_mqtt and not enable_coap and not enable_ws:
        _logger.warning("No protocol bindings have been enabled")

    port_http = conf.port_http if enable_http else None
    port_ws = conf.port_ws if enable_ws else None
    port_coap = conf.port_coap if enable_coap else None
    mqtt_url = conf.mqtt_url if enable_mqtt else None

    if enable_mqtt and not mqtt_url:
        _logger.warning("MQTT is enabled but broker is undefined")

    app_func = _import_app_func(module_path=path, func_name=func)

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(_exception_handler)

    thing_cb, redis_pool = _build_thing_cb(
        redis_url=conf.redis_url,
        loop=loop)

    wot_kwargs = {
        "port_catalogue": conf.port_catalogue,
        "exposed_cb": thing_cb,
        "consumed_cb": thing_cb,
        "port_http": port_http,
        "port_ws": port_ws,
        "port_coap": port_coap,
        "mqtt_url": mqtt_url,
        "hostname": hostname
    }

    _logger.debug("Building WoT entrypoint with args: %s", wot_kwargs)
    wot = wotemu.wotpy.wot.wot_entrypoint(**wot_kwargs)

    asyncio.ensure_future(_start_servient(wot))

    app_args = (wot, conf, loop)
    app_kwargs = {key: val for key, val in func_param}

    _logger.debug(
        "WoT app call signature (positional and keyword):\n%s\n%s",
        pprint.pformat(app_args),
        pprint.pformat(app_kwargs))

    _logger.info("Scheduling task for WoT app: %s", app_func)
    app_task = asyncio.ensure_future(app_func(*app_args, **app_kwargs))

    monitor = None

    if not disable_monitor:
        _logger.info("Scheduling startup task for node monitor")
        ifaces = _get_monitor_ifaces(docker_url=conf.docker_proxy_url)
        monitor = NodeMonitor(redis_url=conf.redis_url, packet_ifaces=ifaces)
        asyncio.ensure_future(monitor.start())

    stop = functools.partial(
        _stop,
        loop=loop,
        app_task=app_task,
        wot=wot,
        redis_pool=redis_pool,
        monitor=monitor,
        lock=asyncio.Lock())

    exit_status = {}

    app_done_cb = functools.partial(
        _app_done_cb,
        stop=stop,
        exit_status=exit_status)

    app_task.add_done_callback(app_done_cb)

    def sig_handler():
        _logger.debug("Received stop signal")
        asyncio.ensure_future(stop())

    for name in {"SIGINT", "SIGTERM"}:
        loop.add_signal_handler(getattr(signal, name), sig_handler)

    try:
        _logger.debug("Running loop")
        loop.run_forever()
    finally:
        _logger.debug("Closing loop")
        loop.close()
        exit_code = exit_status.get("code")

        if exit_code:
            _logger.warning("Exiting with code: %s", exit_code)
            exit(exit_code)
