import asyncio
import datetime
import functools
import json
import logging
import pprint
import random
import time

from wotpy.wot.enums import DataType
from wotpy.wot.td import ThingDescription

_DESCRIPTION = {
    "id": "urn:org:fundacionctic:thing:clock",
    "name": "Clock Thing",
    "properties": {
        "time": {
            "type": DataType.INTEGER,
            "readOnly": True
        }
    },
    "events": {
        "timeEvent": {
            "data": {
                "type": DataType.INTEGER
            }
        },
        "dateEvent": {
            "data": {
                "type": DataType.STRING
            }
        }
    }
}

_TIMEOUT = 10

_logger = logging.getLogger(__name__)


def _time_millis():
    return int(time.time() * 1e3)


async def _time_handler():
    return _time_millis()


def _emit_time(exposed_thing):
    payload = _time_millis()
    _logger.debug("Emitting timeEvent: %s", payload)
    exposed_thing.emit_event("timeEvent", payload)


def _emit_date(exposed_thing):
    payload = datetime.datetime.utcnow().isoformat()
    _logger.debug("Emitting dateEvent: %s", payload)
    exposed_thing.emit_event("dateEvent", payload)


async def _emitter(emit_func, interval):
    interval = float(interval)

    try:
        while True:
            next_time = time.time() + interval
            emit_func()
            sleep = next_time - time.time()
            await asyncio.sleep(max(0, sleep))
    except asyncio.CancelledError:
        _logger.debug("One last event before cancelling: %s", emit_func)
        emit_func()


async def app(wot, conf, loop, interval=2):
    _logger.info("Starting clock app with interval: %s seconds", interval)

    _logger.info(
        "Producing Thing:\n%s",
        pprint.pformat(_DESCRIPTION))

    exposed_thing = wot.produce(json.dumps(_DESCRIPTION))
    exposed_thing.set_property_read_handler("time", _time_handler)
    exposed_thing.expose()

    _logger.debug(
        "Exposed Thing:\n%s",
        pprint.pformat(ThingDescription.from_thing(exposed_thing.thing).to_dict()))

    emit_time = functools.partial(_emit_time, exposed_thing)
    emit_date = functools.partial(_emit_date, exposed_thing)

    time_task = asyncio.ensure_future(_emitter(emit_time, interval=interval))
    date_task = asyncio.ensure_future(_emitter(emit_date, interval=interval))

    try:
        await asyncio.gather(time_task, date_task)
    except asyncio.CancelledError:
        await asyncio.wait_for(asyncio.gather(time_task, date_task), _TIMEOUT)
