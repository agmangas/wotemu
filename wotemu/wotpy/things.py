import asyncio
import logging
import pprint
import time
import uuid
from functools import wraps

import wotpy.wot.consumed.thing
import wotpy.wot.exposed.thing
from wotpy.protocols.enums import InteractionVerbs

_logger = logging.getLogger(__name__)


class VerbCallback:
    def __init__(self, verb, func, call_args, call_kwargs):
        self.verb = verb
        self.func = func
        self.call_args = call_args
        self.call_kwargs = call_kwargs

    @classmethod
    def json_ex(cls, ex):
        return {
            "type": ex.__class__.__name__,
            "message": str(ex)
        } if ex else None

    def __str__(self):
        return "<{}> {}".format(self.__class__.__name__, self.__dict__)

    @property
    def data(self):
        return {
            "thing": self.thing_id,
            "verb": self.verb,
            "name": self.interaction_name,
            "time": time.time(),
            "host": self.hostname,
            "class": self.thing_class
        }

    @property
    def callback(self):
        return self.thing.deco_cb

    @property
    def loop(self):
        try:
            return asyncio.get_running_loop()
        except:
            return asyncio.get_event_loop()

    @property
    def interaction_name(self):
        if self.call_kwargs.get("name", None) is not None:
            return self.call_kwargs["name"]

        if len(self.call_args) >= 2 and self.call_args[1]:
            return self.call_args[1]

        _logger.warning("Undefined interaction name: %s", self)

        return None

    @property
    def thing(self):
        thing = self.call_args[0]
        assert isinstance(thing, (ExposedThing, ConsumedThing))
        return thing

    @property
    def hostname(self):
        return self.thing.servient.hostname

    @property
    def thing_id(self):
        return self.thing.id

    @property
    def thing_class(self):
        return self.thing.__class__.__name__


class RequestVerbCallback(VerbCallback):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._result = None
        self._error = None
        self._init_time = time.time()
        self.latency = None

    @property
    def data(self):
        data = super().data

        if self.latency is None:
            _logger.warning("Called data property with no latency")

        data.update({
            "latency": self.latency,
            "error": self.json_ex(self.error),
            "result": self.result
        })

        return data

    @property
    def result(self):
        return self._result

    @result.setter
    def result(self, val):
        self._error = None
        self._result = val

    @property
    def error(self):
        return self._error

    @error.setter
    def error(self, err):
        self._result = None
        self._error = err

    def update_latency(self):
        self.latency = time.time() - self._init_time

    def create_callback_task(self):
        if not self.callback:
            return

        data = self.data

        _logger.log(
            logging.WARNING if self.error else logging.DEBUG,
            "<%s>\n%s",
            self.__class__.__name__,
            pprint.pformat(data))

        self.loop.create_task(self.callback(data))


class SubscriptionVerbCallback(VerbCallback):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sub_id = uuid.uuid4().hex

    @property
    def data(self):
        data = super().data

        data.update({
            "subscription": self.sub_id
        })

        return data

    def decorate_observable(self, obsv):
        if not self.callback:
            return obsv

        def callback_task(data):
            data.update(self.data)

            _logger.log(
                logging.WARNING if data.get("error") else logging.DEBUG,
                "<%s>\n%s",
                self.__class__.__name__,
                pprint.pformat(data))

            self.loop.create_task(self.callback(data))

        event_key = "event"

        def on_next(item):
            try:
                item_data = item.data.__dict__
            except:
                item_data = item.data

            callback_task({
                event_key: "on_next",
                "item": item_data
            })

        def on_error(err):
            callback_task({
                event_key: "on_error",
                "error": self.json_ex(err)
            })

        def on_completed():
            callback_task({
                event_key: "on_completed"
            })

        def on_subscribe():
            callback_task({
                event_key: "on_subscribe"
            })

        def on_finally():
            callback_task({
                event_key: "on_finally"
            })

        obsv = obsv.do_action(
            on_next=on_next,
            on_error=on_error,
            on_completed=on_completed)

        obsv = obsv.do_on_subscribe(on_subscribe)
        obsv = obsv.do_finally(on_finally)

        return obsv


def _request_deco(verb):
    def deco(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            verb_cb = RequestVerbCallback(
                verb=verb,
                func=func,
                call_args=args,
                call_kwargs=kwargs)

            raised_ex = None

            try:
                result = await func(*args, **kwargs)
                verb_cb.result = result
            except Exception as ex:
                raised_ex = ex
                verb_cb.error = raised_ex

            verb_cb.update_latency()
            verb_cb.create_callback_task()

            if raised_ex is not None:
                raise raised_ex
            else:
                return result

        return wrapper

    return deco


def _subscribe_deco(verb):
    def deco(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            verb_cb = SubscriptionVerbCallback(
                verb=verb,
                func=func,
                call_args=args,
                call_kwargs=kwargs)

            obsv = func(*args, **kwargs)

            return verb_cb.decorate_observable(obsv)

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


class ConsumedThing(wotpy.wot.consumed.thing.ConsumedThing):
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
