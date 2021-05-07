"""
A MongoDB-based historian Thing able to persist property 
values and return them in an aggregated fashion.
"""

import asyncio
import collections
import functools
import json
import logging
import os
import pprint
import time
from datetime import datetime

import motor.motor_asyncio
import pymongo
from wotemu.utils import consume_from_catalogue
from wotpy.wot.td import ThingDescription

_DEFAULT_FALLBACK_DB = "wotemu_mongo_historian"
_DEFAULT_QUERY_SECONDS = 60

_DESCRIPTION = {
    "id": "urn:org:fundacionctic:thing:historian",
    "name": "MongoDB historian Thing",
    "properties": {
        "observedThings": {
            "readOnly": True,
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "servient": {
                        "type": "string"
                    },
                    "thingId": {
                        "type": "string"
                    }
                },
                "required": ["servient", "thingId"]
            }
        }
    },
    "actions": {
        "list": {
            "safe": True,
            "idempotent": False,
            "output": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "thingId": {
                            "type": "string"
                        },
                        "propertyName": {
                            "type": "string"
                        },
                        "servient": {
                            "type": "string"
                        }
                    },
                    "required": ["propertyName", "thingId", "servient"]
                }
            }
        },
        "get": {
            "safe": True,
            "idempotent": False,
            "input": {
                "type": "object",
                "properties": {
                    "fromUnix": {
                        "type": "number"
                    },
                    "toUnix": {
                        "type": "number"
                    },
                    "thingId": {
                        "type": "string"
                    },
                    "propertyName": {
                        "type": "string"
                    },
                    "servient": {
                        "type": "string"
                    },
                    "buckets": {
                        "type": "number"
                    }
                }
            },
            "output": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "unixTime": {
                            "type": "number"
                        },
                        "thingId": {
                            "type": "string"
                        },
                        "propertyName": {
                            "type": "string"
                        },
                        "servient": {
                            "type": "string"
                        },
                        "value": {
                            "type": "string"
                        }
                    },
                    "required": ["unixTime", "propertyName", "thingId", "servient", "value"]
                }
            }
        },
        "write": {
            "safe": False,
            "idempotent": False,
            "input": {
                "type": "object",
                "properties": {
                    "unixTime": {
                        "type": "number"
                    },
                    "propertyName": {
                        "type": "string"
                    },
                    "thingId": {
                        "type": "string"
                    },
                    "servient": {
                        "type": "string"
                    },
                    "value": {
                        "type": "string"
                    }
                },
                "required": ["propertyName", "thingId", "servient", "value"]
            }
        }
    }
}

_logger = logging.getLogger(__name__)


MongoHistorianThing = collections.namedtuple(
    "MongoHistorianThing",
    ["task_observe", "exposed_thing", "observe_stop_event"])


async def _get_aggregated(params_input, motor_client, db_name, query):
    params_input = params_input or {}
    num_buckets = int(params_input.get("buckets", 10))

    pipeline = [
        {
            "$match": query
        },
        {
            "$addFields": {
                "date_str": {
                    "$dateToString": {
                        "format": "%Y%m%d_%H%M%S",
                        "date": "$utc_date"
                    }
                }
            }
        },
        {
            "$bucketAuto": {
                "groupBy": "$date_str",
                "buckets": num_buckets,
                "output": {
                    "utc_date": {"$first": "$utc_date"},
                    "property_name": {"$first": "$property_name"},
                    "thing_id": {"$first": "$thing_id"},
                    "servient": {"$first": "$servient"},
                    "value": {"$first": "$value"}
                }
            }
        },
        {
            "$sort": {"utc_date": 1}
        }
    ]

    _logger.debug("Running pipeline:\n%s", pprint.pformat(pipeline))

    cur = motor_client[db_name].properties.aggregate(pipeline)

    return [
        {
            "thingId": doc["thing_id"],
            "propertyName": doc["property_name"],
            "servient": doc["servient"],
            "value": doc["value"],
            "unixTime": doc["utc_date"].timestamp()
        }
        async for doc in cur
    ]


async def _get(params, motor_client, db_name):
    params_input = params["input"]
    params_input = params_input or {}

    from_unix_default = time.time() - _DEFAULT_QUERY_SECONDS
    from_unix = int(params_input.get("fromUnix", from_unix_default))

    query = {
        "utc_date": {
            "$gte": datetime.utcfromtimestamp(from_unix)
        }
    }

    if params_input.get("toUnix"):
        to_unix = int(params_input["toUnix"])
        query["utc_date"].update({"$lt": datetime.utcfromtimestamp(to_unix)})

    if params_input.get("propertyName"):
        query.update({
            "property_name": {
                "$eq": params_input["propertyName"]
            }
        })

    if params_input.get("thingId"):
        query.update({
            "thing_id": {
                "$eq": params_input["thingId"]
            }
        })

    if params_input.get("servient"):
        query.update({
            "servient": {
                "$eq": params_input["servient"]
            }
        })

    if params_input.get("buckets"):
        return await _get_aggregated(
            params_input=params_input,
            motor_client=motor_client,
            db_name=db_name,
            query=query)

    cur = motor_client[db_name].properties.find(query).sort("utc_date")

    return [
        {
            "thingId": doc["thing_id"],
            "propertyName": doc["property_name"],
            "servient": doc["servient"],
            "value": doc["value"],
            "unixTime": doc["utc_date"].timestamp()
        }
        async for doc in cur
    ]


async def _write(params, motor_client, db_name):
    params_input = params["input"]
    params_input = params_input or {}

    tstamp = params_input.get("unixTime")
    dtime = datetime.utcfromtimestamp(tstamp) if tstamp else datetime.utcnow()

    doc = {
        "utc_date": dtime,
        "property_name": params_input["propertyName"],
        "thing_id": params_input["thingId"],
        "servient": params_input["servient"],
        "value": params_input["value"]
    }

    _logger.debug("Inserting doc: %s", doc)
    result = await motor_client[db_name].properties.insert_one(doc)
    _logger.debug("Inserted: %s", result.inserted_id)


async def _list(params, motor_client, db_name):
    pipeline = [
        {
            "$group": {
                "_id": {
                    "property_name": "$property_name",
                    "thing_id": "$thing_id",
                    "servient": "$servient"
                }
            }
        }
    ]

    _logger.debug("Running pipeline:\n%s", pprint.pformat(pipeline))

    cur = motor_client[db_name].properties.aggregate(pipeline)

    return [
        {
            "propertyName": doc["_id"]["property_name"],
            "thingId": doc["_id"]["thing_id"],
            "servient": doc["_id"]["servient"]
        }
        async for doc in cur
    ]


async def _wait_mongo(mongo_uri, timeout_ping, sleep_iter=1.0):
    now = time.time()
    time_limit = now + timeout_ping

    _logger.info("Waiting for MongoDB (%s secs)", timeout_ping)

    while time.time() < time_limit:
        try:
            motor_client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)
            assert await motor_client.admin.command("ping")
            return True
        except Exception as ex:
            _logger.debug("Still waiting for MongoDB: %s", repr(ex))

        await asyncio.sleep(sleep_iter)

    raise RuntimeError("Timeout waiting for MongoDB")


async def _create_indexes(motor_client, db_name):
    keys = [
        ("utc_date", pymongo.DESCENDING),
        ("property_name", pymongo.DESCENDING),
        ("thing_id", pymongo.DESCENDING),
        ("servient", pymongo.DESCENDING)
    ]

    _logger.info("Creating index: %s", keys)

    await motor_client[db_name].properties.create_index(
        keys,
        name="utc_date_property_name_thing_id_servient",
        background=True)

    keys = [
        ("property_name", pymongo.DESCENDING),
        ("thing_id", pymongo.DESCENDING),
        ("servient", pymongo.DESCENDING)
    ]

    _logger.info("Creating index: %s", keys)

    await motor_client[db_name].properties.create_index(
        keys,
        name="property_name_thing_id_servient",
        background=True)


async def _run_observe_historian_iter(
        wot, port_catalogue, servient_host, thing_id,
        buckets, interval, motor_client, db_name, invoke_timeout):
    to_unix = datetime.utcnow().timestamp()
    from_unix = to_unix - interval

    _logger.debug(
        "Running historian observation iteration (from=%s) (to=%s)",
        datetime.utcfromtimestamp(from_unix),
        datetime.utcfromtimestamp(to_unix))

    cons_thing = await consume_from_catalogue(
        wot=wot,
        port_catalogue=port_catalogue,
        servient_host=servient_host,
        thing_id=thing_id)

    props_list = await cons_thing.actions["list"].invoke(None, timeout=invoke_timeout)

    _logger.debug("Reading properties:\n%s", pprint.pformat(props_list))

    invocation_params = [
        {
            "toUnix": to_unix,
            "fromUnix": from_unix,
            "buckets": buckets,
            "propertyName": prop_item["propertyName"],
            "thingId": prop_item["thingId"],
            "servient": prop_item["servient"]
        }
        for prop_item in props_list
    ]

    invocation_awaitables = [
        cons_thing.actions["get"].invoke(params, timeout=invoke_timeout)
        for params in invocation_params
    ]

    results = await asyncio.gather(*invocation_awaitables, return_exceptions=True)

    write_params = [
        {
            "input": {
                "unixTime": item["unixTime"],
                "propertyName": item["propertyName"],
                "thingId": item["thingId"],
                "servient": item["servient"],
                "value": item["value"]
            }
        }
        for results_list in results
        for item in results_list
        if not isinstance(results_list, Exception)
    ]

    write_awaitables = [
        _write(params=params, motor_client=motor_client, db_name=db_name)
        for params in write_params
    ]

    await asyncio.gather(*write_awaitables, return_exceptions=True)


async def _start_observe_historian_task(
        wot, port_catalogue, servient_host, thing_id,
        buckets, interval, motor_client, db_name, stop_event, invoke_timeout=40):
    run_iter = functools.partial(
        _run_observe_historian_iter,
        wot=wot,
        port_catalogue=port_catalogue,
        servient_host=servient_host,
        thing_id=thing_id,
        buckets=buckets,
        interval=interval,
        motor_client=motor_client,
        db_name=db_name,
        invoke_timeout=invoke_timeout)

    prev_time = None
    next_time = time.time() + interval

    while not stop_event.is_set():
        now = time.time()

        if now >= next_time:
            if prev_time:
                delta = now - prev_time
                _logger.debug("Historian observation task delta: %s s.", delta)

            prev_time = now
            next_time = now + interval

            try:
                await run_iter()
            except Exception as ex:
                _logger.warning("Error in historian iteration: %s", repr(ex))

        await asyncio.sleep(1)


async def _read_insert_property(consumed_thing, name, thing_id, servient_host, motor_client, db_name):
    try:
        _logger.debug("Reading property (%s)", name)
        val = await consumed_thing.properties[name].read()
        _logger.debug("Read property (%s=%s)", name, val)
    except Exception as ex:
        _logger.warning("Error reading (%s): %s", name, repr(ex))
        return

    params = {
        "input": {
            "propertyName": name,
            "thingId": thing_id,
            "servient": servient_host,
            "value": val
        }
    }

    await _write(params=params, motor_client=motor_client, db_name=db_name)


async def _run_observe_thing_iter(wot, port_catalogue, motor_client, db_name, servient_host, thing_id):
    cons_thing = await consume_from_catalogue(
        wot=wot,
        port_catalogue=port_catalogue,
        servient_host=servient_host,
        thing_id=thing_id)

    read_insert_kwargs = [
        {
            "consumed_thing": cons_thing,
            "name": name,
            "thing_id": thing_id,
            "servient_host": servient_host,
            "motor_client": motor_client,
            "db_name": db_name
        }
        for name in cons_thing.properties
    ]

    read_insert_awaitables = [
        _read_insert_property(**item)
        for item in read_insert_kwargs
    ]

    await asyncio.gather(*read_insert_awaitables, return_exceptions=True)


async def _start_observe_thing_task(wot, port_catalogue, motor_client, db_name, observed_things, interval, stop_event):
    run_iter = functools.partial(
        _run_observe_thing_iter,
        wot=wot,
        port_catalogue=port_catalogue,
        motor_client=motor_client,
        db_name=db_name)

    while not stop_event.is_set():
        iter_awaitables = [
            run_iter(
                servient_host=item["servient_host"],
                thing_id=item["thing_id"])
            for item in observed_things
        ]

        await asyncio.gather(*iter_awaitables, return_exceptions=True)
        await asyncio.sleep(interval)


async def _start_observe_task(
        wot, port_catalogue, observed_things, motor_client, db_name, interval, stop_event,
        downlink_servient_host, downlink_thing_id, downlink_buckets, downlink_interval):
    awaitables = []

    if observed_things and len(observed_things) > 0:
        thing_awaitable = _start_observe_thing_task(
            wot=wot,
            port_catalogue=port_catalogue,
            motor_client=motor_client,
            db_name=db_name,
            observed_things=observed_things,
            interval=interval,
            stop_event=stop_event)

        awaitables.append(thing_awaitable)

    if downlink_servient_host and downlink_thing_id:
        historian_awaitable = _start_observe_historian_task(
            wot=wot,
            port_catalogue=port_catalogue,
            servient_host=downlink_servient_host,
            thing_id=downlink_thing_id,
            buckets=downlink_buckets,
            interval=downlink_interval,
            motor_client=motor_client,
            db_name=db_name,
            stop_event=stop_event)

        awaitables.append(historian_awaitable)

    await asyncio.gather(*awaitables, return_exceptions=False)


async def _things_handler(observed_things):
    return [
        {
            "servient": item["servient_host"],
            "thingId": item["thing_id"]
        }
        for item in observed_things
    ]


async def produce_thing(
        wot, conf, mongo_uri, db_name=None, observed_things=None, interval=5, timeout_ping=60,
        downlink_servient_host=None, downlink_thing_id=None, downlink_buckets=1, downlink_interval=60):
    downlink_args = [downlink_servient_host, downlink_thing_id]

    if any(downlink_args) and not all(downlink_args):
        raise ValueError("Partially defined downlink parameters")

    downlink_buckets = int(downlink_buckets)
    downlink_interval = int(downlink_interval)

    await _wait_mongo(mongo_uri=mongo_uri, timeout_ping=timeout_ping)

    _logger.info(
        "Producing Thing:\n%s",
        pprint.pformat(_DESCRIPTION))

    _logger.info("Connecting to MongoDB: %s", mongo_uri)

    motor_client = motor.motor_asyncio.AsyncIOMotorClient(mongo_uri)
    assert await motor_client.admin.command("ping")
    db_name = db_name or os.getenv("SERVICE_NAME", _DEFAULT_FALLBACK_DB)

    _logger.info("MongoDB connection OK (db: %s)", db_name)

    await _create_indexes(motor_client=motor_client, db_name=db_name)

    handler_get = functools.partial(
        _get,
        motor_client=motor_client,
        db_name=db_name)

    handler_write = functools.partial(
        _write,
        motor_client=motor_client,
        db_name=db_name)

    handler_list = functools.partial(
        _list,
        motor_client=motor_client,
        db_name=db_name)

    try:
        observed_things = observed_things or []
        observed_things = json.loads(observed_things)
    except:
        pass

    things_handler = functools.partial(
        _things_handler,
        observed_things=observed_things)

    exposed_thing = wot.produce(json.dumps(_DESCRIPTION))
    exposed_thing.set_action_handler("get", handler_get)
    exposed_thing.set_action_handler("write", handler_write)
    exposed_thing.set_action_handler("list", handler_list)
    exposed_thing.set_property_read_handler("observedThings", things_handler)

    stop_event = asyncio.Event()

    task_observe = asyncio.ensure_future(_start_observe_task(
        wot=wot,
        port_catalogue=conf.port_catalogue,
        observed_things=observed_things,
        motor_client=motor_client,
        db_name=db_name,
        interval=interval,
        stop_event=stop_event,
        downlink_servient_host=downlink_servient_host,
        downlink_thing_id=downlink_thing_id,
        downlink_buckets=downlink_buckets,
        downlink_interval=downlink_interval))

    return MongoHistorianThing(
        task_observe=task_observe,
        exposed_thing=exposed_thing,
        observe_stop_event=stop_event)


async def app(wot, conf, loop, *args, **kwargs):
    historian_thing = await produce_thing(wot=wot, conf=conf, *args, **kwargs)
    historian_thing.exposed_thing.expose()

    td = ThingDescription.from_thing(historian_thing.exposed_thing.thing)
    _logger.debug("Exposed Thing:\n%s", pprint.pformat(td.to_dict()))

    try:
        await historian_thing.task_observe
    except asyncio.CancelledError:
        historian_thing.observe_stop_event.set()
        await asyncio.wait_for(historian_thing.task_observe, timeout=10)
