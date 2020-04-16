import asyncio
import datetime
import json
import logging
import pprint
import random
import time

from wotpy.wot.enums import DataType
from wotpy.wot.td import ThingDescription

_DESCRIPTION = {
    "id": "urn:org:fundacionctic:thing:dummy",
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

_logger = logging.getLogger(__name__)


def _time_millis():
    return int(time.time() * 1e3)


async def _time_handler():
    return _time_millis()


async def _event_wait():
    lambd = 1.0 / float(_EVENT_MEAN_WAIT)
    await asyncio.sleep(random.expovariate(lambd))


async def app(wot, loop):
    _logger.debug("Producing Thing:\n%s", pprint.pformat(_DESCRIPTION))

    exposed_thing = wot.produce(json.dumps(_DESCRIPTION))
    exposed_thing.set_property_read_handler("time", _time_handler)

    async def time_emitter():
        while True:
            payload = _time_millis()
            _logger.debug("Emitting timeEvent: %s", payload)
            exposed_thing.emit_event("timeEvent", payload)
            await _event_wait()

    async def date_emitter():
        while True:
            payload = datetime.datetime.utcnow().isoformat()
            _logger.debug("Emitting dateEvent: %s", payload)
            exposed_thing.emit_event("dateEvent", payload)
            await _event_wait()

    exposed_thing.expose()

    _logger.debug(
        "Exposed Thing:\n%s",
        pprint.pformat(ThingDescription.from_thing(exposed_thing.thing).to_dict()))

    time_task = asyncio.ensure_future(time_emitter())
    date_task = asyncio.ensure_future(date_emitter())

    await asyncio.gather(time_task, date_task)
