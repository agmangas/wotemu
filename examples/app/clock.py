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
    "name": "Benchmark Thing",
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

_EVENT_MEAN_WAIT = 5
_TIMEOUT = 10

_logger = logging.getLogger("wotsim.clock.app")


def _time_millis():
    return int(time.time() * 1e3)


async def _time_handler():
    return _time_millis()


async def _event_wait():
    lambd = 1.0 / float(_EVENT_MEAN_WAIT)
    await asyncio.sleep(random.expovariate(lambd))


def _emit_time(exposed_thing):
    payload = _time_millis()
    _logger.debug("Emitting timeEvent: %s", payload)
    exposed_thing.emit_event("timeEvent", payload)


def _emit_date(exposed_thing):
    payload = datetime.datetime.utcnow().isoformat()
    _logger.debug("Emitting dateEvent: %s", payload)
    exposed_thing.emit_event("dateEvent", payload)


async def _emitter(emit_func):
    try:
        while True:
            emit_func()
            await _event_wait()
    except asyncio.CancelledError:
        _logger.debug("One last event before cancelling: %s", emit_func)
        emit_func()


async def app(wot, conf, loop):
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

    time_task = asyncio.ensure_future(_emitter(emit_time))
    date_task = asyncio.ensure_future(_emitter(emit_date))

    try:
        await asyncio.gather(time_task, date_task)
    except asyncio.CancelledError:
        await asyncio.wait_for(asyncio.gather(time_task, date_task), _TIMEOUT)
