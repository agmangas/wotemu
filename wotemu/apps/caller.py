"""
Invokes all the actions from the Thing 
passed as argument in a periodic fashion.
"""

import asyncio
import json
import logging
import pprint
import random

from wotemu.utils import consume_from_catalogue, wait_node

_logger = logging.getLogger(__name__)


def _log_result(res, max_len=1024):
    res_str = pprint.pformat(res)

    if len(res_str) > max_len:
        res_str = f"{res_str[:max_len]} [...]"

    _logger.debug("Invocation result:\n%s", res_str)


async def _invoke(consumed_thing, name, params, timeout, max_log_len=512):
    if name in params and not params[name]:
        _logger.debug("Skipping invocation for action: %s", name)
        return

    try:
        params = params.get(name, None)
        _logger.debug("Invoking %s with params: %s", name, params)
        res = await consumed_thing.actions[name].invoke(params, timeout=timeout)
        _log_result(res)
    except Exception:
        _logger.warning("Invocation error (%s)", name, exc_info=True)


async def app(wot, conf, loop, servient_host, thing_id, params=None, timeout=300, lambd=2):
    try:
        params = json.loads(params)
    except:
        _logger.debug("Could not parse JSON-serialized params")

    params = params or {}
    lambd = float(lambd)

    _logger.info(
        "Starting caller app for remote %s :: %s (lambda=%s)",
        servient_host, thing_id, lambd)

    await wait_node(conf=conf, name=servient_host, thing_ids=[thing_id])

    consumed_thing = await consume_from_catalogue(
        wot=wot,
        port_catalogue=conf.port_catalogue,
        servient_host=servient_host,
        thing_id=thing_id)

    while True:
        for name in consumed_thing.actions:
            await _invoke(
                consumed_thing=consumed_thing,
                name=name,
                params=params,
                timeout=timeout)

        await asyncio.sleep(random.expovariate(lambd))
