import asyncio
import logging
import time
import uuid
from functools import wraps

import wotpy.wot.exposed.thing
from wotpy.protocols.enums import InteractionVerbs

_logger = logging.getLogger(__name__)


def _request_deco(verb):
    def deco(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            now = time.time()
            error = None

            cb_data = {
                "verb": verb,
                "params": (args, kwargs),
                "time": int(now * 1e3),
            }

            try:
                result = await func(*args, **kwargs)
                cb_data.update({"result": result})
            except Exception as ex:
                error = ex
                cb_data.update({"error": ex})

            latency = time.time() - now
            cb_data.update({"latency": int(latency * 1e3)})

            callback = args[0].deco_cb

            if callback:
                level = logging.WARNING if error else logging.DEBUG
                _logger.log(level, "Callback [%s] %s", verb, cb_data)
                loop = asyncio.get_running_loop()
                loop.create_task(callback(cb_data))

            if error:
                raise error
            else:
                return result

        return wrapper

    return deco


def _subscribe_deco(verb):
    def deco(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            obsv = func(*args, **kwargs)
            callback = args[0].deco_cb

            if not callback:
                return obsv

            loop = asyncio.get_running_loop()
            sub_id = uuid.uuid4().hex
            now = time.time()

            base_data = {
                "verb": verb,
                "params": (args, kwargs),
                "time": int(now * 1e3),
                "id": sub_id
            }

            def callback_task(data):
                cb_data = {
                    **base_data,
                    **data
                }

                _logger.debug("Callback [%s] %s", verb, cb_data)
                loop.create_task(callback(cb_data))

            def on_next(item):
                callback_task({"on_next": item})

            def on_error(err):
                callback_task({"on_error": err})

            def on_completed():
                callback_task({"on_completed": True})

            def on_subscribe():
                callback_task({"on_subscribe": True})

            def on_finally():
                callback_task({"on_finally": True})

            obsv = obsv.do_action(
                on_next=on_next,
                on_error=on_error,
                on_completed=on_completed)

            obsv = obsv.do_on_subscribe(on_subscribe)
            obsv = obsv.do_finally(on_finally)

            return obsv

        return wrapper

    return deco


class ExposedThing(wotpy.wot.exposed.thing.ExposedThing):
    def __init__(self, *args, **kwargs):
        self.deco_cb = kwargs.pop("deco_cb", None)
        super().__init__(*args, **kwargs)

    @_request_deco(InteractionVerbs.INVOKE_ACTION)
    async def invoke_action(self, *args, **kwargs):
        return await super().invoke_action(*args, **kwargs)

    @_request_deco(InteractionVerbs.WRITE_PROPERTY)
    async def write_property(self, *args, **kwargs):
        return await super().write_property(*args, **kwargs)

    @_request_deco(InteractionVerbs.READ_PROPERTY)
    async def read_property(self, *args, **kwargs):
        return await super().read_property(*args, **kwargs)

    @_subscribe_deco(InteractionVerbs.SUBSCRIBE_EVENT)
    def on_event(self, *args, **kwargs):
        return super().on_event(*args, **kwargs)

    @_subscribe_deco(InteractionVerbs.OBSERVE_PROPERTY)
    def on_property_change(self, *args, **kwargs):
        return super().on_property_change(*args, **kwargs)
