import asyncio
import logging

from wotemu.utils import consume_from_catalogue, wait_node

_logger = logging.getLogger(__name__)


async def _read(consumed_thing, name):
    try:
        _logger.debug("Reading: %s", name)
        val = await consumed_thing.properties[name].read()
        _logger.debug("Read %s = %s", name, val)
    except Exception as ex:
        _logger.warning("Error reading %s: %s", name, ex)


async def app(wot, conf, loop, servient_host, thing_id, interval=5):
    await wait_node(conf=conf, name=servient_host)

    consumed_thing = await consume_from_catalogue(
        wot=wot,
        port_catalogue=conf.port_catalogue,
        servient_host=servient_host,
        thing_id=thing_id)

    while True:
        for name in consumed_thing.properties:
            await _read(consumed_thing, name)

        await asyncio.sleep(interval)
