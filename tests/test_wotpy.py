import asyncio
import json
import random

import pytest
from wotpy.protocols.enums import InteractionVerbs
from wotpy.wot.td import ThingDescription

from wotsim.wotpy.consumed import ConsumedThing
from wotsim.wotpy.exposed import ExposedThing
from wotsim.wotpy.wot import wot_entrypoint

TD_EXAMPLE = {
    "id": "urn:org:fundacionctic:thing:testthing",
    "name": "Test Thing",
    "properties": {
        "testProp": {
            "description": "Test property",
            "type": "number",
            "readOnly": False,
            "observable": True
        }
    }
}

MAX_DUMMY_SLEEP_SECS = 0.15


async def dummy_sleep():
    await asyncio.sleep(random.uniform(0, MAX_DUMMY_SLEEP_SECS))


async def max_sleep():
    await asyncio.sleep(MAX_DUMMY_SLEEP_SECS * 2)


@pytest.fixture
def decorated_wotpy(unused_tcp_port_factory):
    port_catalogue = unused_tcp_port_factory()
    port_http = unused_tcp_port_factory()
    port_ws = unused_tcp_port_factory()

    exposed_data = []

    async def exposed_cb(data):
        await dummy_sleep()
        exposed_data.append(data)

    wot = wot_entrypoint(
        port_catalogue=port_catalogue,
        port_http=port_http,
        port_ws=port_ws,
        hostname="localhost",
        exposed_cb=exposed_cb)

    return {
        "wot": wot,
        "exposed_data": exposed_data
    }


@pytest.mark.asyncio
async def test_decorated_exposed(event_loop, decorated_wotpy):
    wot = decorated_wotpy["wot"]
    exposed_thing = wot.produce(model=json.dumps(TD_EXAMPLE))
    assert isinstance(exposed_thing, ExposedThing)


@pytest.mark.asyncio
async def test_decorated_consumed(event_loop, decorated_wotpy):
    wot = decorated_wotpy["wot"]
    consumed_thing = wot.consume(json.dumps(TD_EXAMPLE))
    assert isinstance(consumed_thing, ConsumedThing)


@pytest.mark.asyncio
async def test_read_write_property(decorated_wotpy):
    wot = decorated_wotpy["wot"]
    exposed_data = decorated_wotpy["exposed_data"]

    exposed_thing = wot.produce(model=json.dumps(TD_EXAMPLE))
    exposed_thing.expose()
    await exposed_thing.servient.start()

    td_str = ThingDescription.from_thing(exposed_thing.thing).to_str()
    consumed_thing = wot.consume(td_str)

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
async def test_read_property_error(decorated_wotpy):
    wot = decorated_wotpy["wot"]
    exposed_data = decorated_wotpy["exposed_data"]

    handler_ex = Exception()

    async def read_handler():
        raise handler_ex

    exposed_thing = wot.produce(model=json.dumps(TD_EXAMPLE))
    exposed_thing.set_property_read_handler("testProp", read_handler)
    exposed_thing.expose()
    await exposed_thing.servient.start()

    read_error = None

    try:
        await exposed_thing.properties["testProp"].read()
    except Exception as ex:
        read_error = ex

    assert read_error is handler_ex

    await max_sleep()

    assert any(
        item.get("verb") == InteractionVerbs.READ_PROPERTY and
        item.get("error") and
        item.get("result", None) is None
        for item in exposed_data)


@pytest.mark.asyncio
async def test_observe_property(event_loop, decorated_wotpy):
    wot = decorated_wotpy["wot"]
    exposed_data = decorated_wotpy["exposed_data"]

    exposed_thing = wot.produce(model=json.dumps(TD_EXAMPLE))
    exposed_thing.expose()
    await exposed_thing.servient.start()

    td_str = ThingDescription.from_thing(exposed_thing.thing).to_str()
    consumed_thing = wot.consume(td_str)

    assert len(exposed_data) == 0

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

    consumed_thing.properties["testProp"].subscribe(on_next=on_next)
    write_task = event_loop.create_task(write_loop())
    sub_value = await sub_future
    assert sub_value == val
    write_task.cancel()

    await max_sleep()

    assert any(
        item.get("verb") == InteractionVerbs.OBSERVE_PROPERTY and
        item.get("on_next")
        for item in exposed_data)

    await exposed_thing.servient.shutdown()
