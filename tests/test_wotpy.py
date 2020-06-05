import asyncio
import json
import random

import pytest
from tests.conftest import TD_EXAMPLE
from wotpy.protocols.enums import InteractionVerbs
from wotpy.wot.td import ThingDescription

from wotemu.wotpy.things import ConsumedThing, ExposedThing
from wotemu.wotpy.wot import wot_entrypoint

MAX_DUMMY_SLEEP_SECS = 0.15
WOT_HOSTNAME = "127.0.0.1"


async def dummy_sleep():
    await asyncio.sleep(random.uniform(0, MAX_DUMMY_SLEEP_SECS))


async def max_sleep():
    await asyncio.sleep(MAX_DUMMY_SLEEP_SECS * 2)


def decorated_wotpy_params():
    params = [
        "port_http",
        "port_ws"
    ]

    try:
        from wotpy.protocols.coap.server import CoAPServer
        params.append("port_coap")
    except NotImplementedError:
        pass

    return params


@pytest.fixture(params=decorated_wotpy_params())
def decorated_wotpy(request, unused_tcp_port_factory):
    exposed_data = []

    async def exposed_cb(data):
        await dummy_sleep()
        exposed_data.append(data)

    consumed_data = []

    async def consumed_cb(data):
        await dummy_sleep()
        consumed_data.append(data)

    port_catalogue = unused_tcp_port_factory()

    wot_kwargs = {
        request.param: unused_tcp_port_factory()
    }

    wot = wot_entrypoint(
        port_catalogue=port_catalogue,
        hostname=WOT_HOSTNAME,
        exposed_cb=exposed_cb,
        consumed_cb=consumed_cb,
        **wot_kwargs)

    return {
        "wot": wot,
        "exposed_data": exposed_data,
        "consumed_data": consumed_data
    }


async def build_things(wot):
    exposed_thing = wot.produce(model=json.dumps(TD_EXAMPLE))
    exposed_thing.expose()
    await exposed_thing.servient.start()

    td_str = ThingDescription.from_thing(exposed_thing.thing).to_str()
    consumed_thing = wot.consume(td_str)

    return exposed_thing, consumed_thing


@pytest.mark.asyncio
async def text_exposed_decorated(event_loop, decorated_wotpy):
    wot = decorated_wotpy["wot"]
    exposed_thing = wot.produce(model=json.dumps(TD_EXAMPLE))
    assert isinstance(exposed_thing, ExposedThing)


@pytest.mark.asyncio
async def test_consumed_decorated(event_loop, decorated_wotpy):
    wot = decorated_wotpy["wot"]
    consumed_thing = wot.consume(json.dumps(TD_EXAMPLE))
    assert isinstance(consumed_thing, ConsumedThing)


@pytest.mark.asyncio
async def test_exposed_rw_property(decorated_wotpy):
    wot = decorated_wotpy["wot"]
    exposed_data = decorated_wotpy["exposed_data"]

    _, consumed_thing = await build_things(wot)

    assert len(exposed_data) == 0

    val = int(random.random() * 100)
    await consumed_thing.properties["testProp"].write(val)
    read_val = await consumed_thing.properties["testProp"].read()
    assert read_val == val

    await max_sleep()

    assert any(
        item.get("verb") == InteractionVerbs.READ_PROPERTY and
        item.get("result")
        for item in exposed_data)

    assert any(
        item.get("verb") == InteractionVerbs.WRITE_PROPERTY
        for item in exposed_data)


@pytest.mark.asyncio
async def test_exposed_error(decorated_wotpy):
    wot = decorated_wotpy["wot"]
    exposed_data = decorated_wotpy["exposed_data"]

    async def read_handler():
        raise Exception

    exposed_thing, _ = await build_things(wot)
    exposed_thing.set_property_read_handler("testProp", read_handler)

    with pytest.raises(Exception):
        await exposed_thing.properties["testProp"].read()

    await max_sleep()

    assert any(
        item.get("verb") == InteractionVerbs.READ_PROPERTY and
        item.get("error") and
        item.get("result", None) is None
        for item in exposed_data)


@pytest.mark.asyncio
async def test_exposed_observe_property(event_loop, decorated_wotpy):
    wot = decorated_wotpy["wot"]
    consumed_data = decorated_wotpy["consumed_data"]

    exposed_thing, consumed_thing = await build_things(wot)

    assert len(consumed_data) == 0

    val = int(random.random() * 100)

    async def write_loop():
        try:
            while True:
                exposed_thing.properties["testProp"].write(val)
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass

    sub_future = event_loop.create_future()

    def on_next(item):
        if not sub_future.done():
            sub_future.set_result(item.data.value)

    sub = consumed_thing.properties["testProp"].subscribe(on_next=on_next)
    write_task = event_loop.create_task(write_loop())
    sub_value = await sub_future
    assert sub_value == val
    write_task.cancel()

    await max_sleep()

    assert any(
        item.get("verb") == InteractionVerbs.OBSERVE_PROPERTY and
        item.get("event") == "on_next" and
        item.get("item")
        for item in consumed_data)

    sub.dispose()
    await exposed_thing.servient.shutdown()
    await max_sleep()
