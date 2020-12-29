import asyncio
import logging

from wotemu.utils import consume_from_catalogue, wait_node

_logger = logging.getLogger(__name__)


async def _invoke(consumed_thing, name, params, timeout):
    try:
        params = params or {}
        params = params.get(name, None)
        _logger.debug("Invoking %s with params: %s", name, params)
        res = await consumed_thing.actions[name].invoke(params, timeout=timeout)
        _logger.debug("Invocation result: %s", res)
    except Exception as ex:
        _logger.warning("Invocation error (%s): %s", name, ex)


async def app(wot, conf, loop, servient_host, thing_id, params=None, timeout=300, interval=5):
    await wait_node(conf=conf, name=servient_host)

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

        await asyncio.sleep(interval)
