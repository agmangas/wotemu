import functools
import json
import random

import pytest
from tests.conftest import TD_EXAMPLE
from wotpy.wot.td import ThingDescription

from wotemu.wotpy.redis import redis_thing_callback
from wotemu.wotpy.wot import wot_entrypoint

WOT_HOSTNAME = "127.0.0.1"


@pytest.mark.asyncio
async def test_redis_callback(redis, unused_tcp_port_factory):
    redis_cb = functools.partial(redis_thing_callback, client=redis)

    wot = wot_entrypoint(
        port_catalogue=unused_tcp_port_factory(),
        hostname=WOT_HOSTNAME,
        exposed_cb=redis_cb,
        consumed_cb=redis_cb,
        port_http=unused_tcp_port_factory())

    exposed_thing = wot.produce(model=json.dumps(TD_EXAMPLE))
    exposed_thing.expose()
    await exposed_thing.servient.start()

    td_str = ThingDescription.from_thing(exposed_thing.thing).to_str()
    consumed_thing = wot.consume(td_str)

    _cur, keys = await redis.scan(b"0")
    assert len(keys) == 0

    val = int(random.random() * 100)
    await consumed_thing.properties["testProp"].write(val)
    read_val = await consumed_thing.properties["testProp"].read()
    assert read_val == val

    _cur, keys = await redis.scan(b"0")
    assert len(keys) > 0
