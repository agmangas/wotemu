import asyncio
import functools
import importlib
import inspect
import logging
import os
import sys

import aioredis

import wotsim.wotpy.redis
import wotsim.wotpy.wot

_logger = logging.getLogger(__name__)


async def _dummy_thing_cb(*args, **kwargs):
    pass


def _build_thing_cb(redis_url, loop):
    if not redis_url:
        _logger.debug("Using dummy Thing callback")
        return _dummy_thing_cb

    _logger.debug("Creating Redis pool with URL: %s", redis_url)

    redis_pool = loop.run_until_complete(
        aioredis.create_redis_pool(redis_url))

    return functools.partial(
        wotsim.wotpy.redis.redis_thing_callback,
        client=redis_pool)


def _import_app_func(module_path, func_name):
    _logger.debug("Attempting to import from: %s", module_path)

    path_root, path_base = os.path.split(module_path)

    if path_root not in sys.path:
        sys.path.insert(0, path_root)

    mod_name, _ext = os.path.splitext(path_base)
    mod_import = importlib.import_module(mod_name)
    mod_dir = dir(mod_import)

    _logger.debug("Imported: %s", mod_import)
    _logger.debug("dir(%s): %s", mod_import, mod_dir)

    if func_name not in mod_dir:
        raise Exception(
            "Module {} does not contain function '{}'".format(mod_import, func_name))

    app_func = getattr(mod_import, func_name)
    app_func_sig = inspect.signature(app_func)

    _logger.debug("Function (%s) signature: %s", app_func, app_func_sig)

    if len(app_func_sig.parameters) < 1:
        raise Exception(
            "Function {} should take at least one parameter".format(app_func))

    return app_func


def run_app(path, func, port_catalogue, port_http, port_coap, port_ws, mqtt_url, redis_url):
    port_http = port_http if port_http else None
    port_ws = port_ws if port_ws else None
    port_coap = port_coap if port_coap else None
    mqtt_url = mqtt_url if mqtt_url else None

    loop = asyncio.get_event_loop()
    app_func = _import_app_func(module_path=path, func_name=func)
    thing_cb = _build_thing_cb(redis_url=redis_url, loop=loop)

    wot_entry = wotsim.wotpy.wot.wot_entrypoint(
        port_catalogue=port_catalogue,
        exposed_cb=thing_cb,
        consumed_cb=thing_cb,
        port_http=port_http,
        port_ws=port_ws,
        port_coap=port_coap,
        mqtt_url=mqtt_url)

    loop.run_until_complete(app_func(wot_entry))
    loop.close()
