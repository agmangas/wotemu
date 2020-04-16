import asyncio
import functools
import importlib
import inspect
import logging
import os
import pprint
import signal
import sys

import aioredis

import wotsim.wotpy.redis
import wotsim.wotpy.wot

_TIMEOUT = 15

_logger = logging.getLogger(__name__)


def _import_app_func(module_path, func_name):
    _logger.debug("Attempting to import from: %s", module_path)

    path_root, path_base = os.path.split(module_path)

    if path_root not in sys.path:
        sys.path.insert(0, path_root)

    mod_name, _ext = os.path.splitext(path_base)
    mod_import = importlib.import_module(mod_name)
    mod_dir = dir(mod_import)

    _logger.info("Imported: %s", mod_import)
    _logger.debug("dir(%s): %s", mod_import, mod_dir)

    if func_name not in mod_dir:
        raise Exception(
            "Module {} does not contain function '{}'".format(mod_import, func_name))

    app_func = getattr(mod_import, func_name)
    app_func_sig = inspect.signature(app_func)

    _logger.debug("Function (%s) signature: %s", app_func, app_func_sig)

    if len(app_func_sig.parameters) < 2:
        raise Exception(
            "Function {} should take at least two parameters".format(app_func))

    return app_func


def _build_thing_cb(redis_url, loop):
    async def dummy_cb(*args, **kwargs):
        pass

    if not redis_url:
        return dummy_cb, None

    _logger.debug("Creating Redis pool with URL: %s", redis_url)

    redis_pool = loop.run_until_complete(
        aioredis.create_redis_pool(redis_url))

    redis_cb = functools.partial(
        wotsim.wotpy.redis.redis_thing_callback,
        client=redis_pool)

    return redis_cb, redis_pool


def _exception_handler(loop, context):
    level = logging.ERROR if loop.is_running() else logging.DEBUG
    _logger.log(level, "Exception in loop:\n%s", pprint.pformat(context))


async def _start_servient(wot):
    _logger.debug("Starting Servient: %s", wot.servient)
    await wot.servient.start()


async def _stop_servient(wot):
    try:
        _logger.debug("Shutting down Servient: %s", wot.servient)
        await wot.servient.shutdown()
    except Exception as ex:
        _logger.warning("Error in Servient shutdown: %s", ex)


async def _stop_redis(redis_pool):
    if not redis_pool:
        return

    try:
        _logger.debug("Closing Redis")
        redis_pool.close()
        await redis_pool.wait_closed()
    except Exception as ex:
        _logger.warning("Error in Redis shutdown: %s", ex)


def run_app(path, func, port_catalogue, port_http, port_coap, port_ws, mqtt_url, redis_url, hostname):
    port_http = port_http if port_http else None
    port_ws = port_ws if port_ws else None
    port_coap = port_coap if port_coap else None
    mqtt_url = mqtt_url if mqtt_url else None

    app_func = _import_app_func(module_path=path, func_name=func)

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(_exception_handler)

    thing_cb, redis_pool = _build_thing_cb(redis_url=redis_url, loop=loop)

    wot_kwargs = {
        "port_catalogue": port_catalogue,
        "exposed_cb": thing_cb,
        "consumed_cb": thing_cb,
        "port_http": port_http,
        "port_ws": port_ws,
        "port_coap": port_coap,
        "mqtt_url": mqtt_url,
        "hostname": hostname
    }

    _logger.debug("Building WoT entrypoint with args: %s", wot_kwargs)
    wot = wotsim.wotpy.wot.wot_entrypoint(**wot_kwargs)

    asyncio.ensure_future(_start_servient(wot))
    app_task = asyncio.ensure_future(app_func(wot, loop))

    async def stop():
        try:
            _logger.debug("Cancelling WoT app task: %s", app_task)
            app_task.cancel()
            await asyncio.wait_for(app_task, _TIMEOUT)
        except Exception:
            _logger.warning("Error on WoT app cancelation", exc_info=True)

        await _stop_servient(wot)
        await _stop_redis(redis_pool)

        _logger.debug("Stopping loop")
        loop.stop()

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
