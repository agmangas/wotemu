import asyncio
import json
import logging
import pprint
import time

from wotpy.wot.enums import DataType

_logger = logging.getLogger(__name__)

_DESCRIPTION = {
    "id": "urn:org:fundacionctic:thing:worker",
    "name": "Callable Thing",
    "actions": {
        "doWork": {
            "safe": True,
            "idempotent": False,
            "input": {
                "type": DataType.OBJECT
            },
            "output": {
                "type": DataType.OBJECT
            }
        }
    }
}


async def _action_handler(params):
    params = params or {}
    params_input = params.get("input", {}) or {}

    time_step = float(params_input.get("step", 0.5))
    time_total = float(params_input.get("total", 3.0))
    time_sleep = float(params_input.get("sleep", 0.1))

    stamp_end = time.time() + time_total

    while time.time() < stamp_end:
        stamp_step_end = time.time() + time_step

        while time.time() < stamp_step_end:
            time.time() ** 2

        await asyncio.sleep(time_sleep)

    return {"ret": params_input.get("return", time.time())}


async def app(wot, conf, loop):
    _logger.info(
        "Producing Thing:\n%s",
        pprint.pformat(_DESCRIPTION))

    exposed_thing = wot.produce(json.dumps(_DESCRIPTION))
    exposed_thing.set_action_handler("doWork", _action_handler)
    exposed_thing.expose()
