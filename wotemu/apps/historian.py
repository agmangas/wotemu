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
_DEFAULT_TIMEOUT_PING = 60
_DEFAULT_INSERT_INTERVAL = 5

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
                "required": ["servient", "thing"]
            }
        }
    },
    "actions": {
        "get": {
            "safe": True,
            "idempotent": False,
            "input": {
                "type": "object",
                "properties": {
                    "lastSeconds": {
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
                    "aggregate": {
                        "type": "string",
                        "enum": ["second", "minute", "hour"]
                    }
                },
                "required": ["propertyName"]
            },
            "output": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "isoDate": {
                            "type": "string"
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
                    "required": ["propertyName", "value"]
                }
            }
        },
        "write": {
            "safe": False,
            "idempotent": False,
            "input": {
                "type": "object",
                "properties": {
                    "timestamp": {
                        "type": "number"
                    },
                    "propertyName": {
                        "type": "string"
                    },
                    "thingId": {
                        "type": "string"
                    },
                    "value": {
                        "type": "string"
                    }
                },
                "required": ["propertyName", "value"]
            }
        }
    }
}

_logger = logging.getLogger(__name__)


MongoHistorianThing = collections.namedtuple(
    "MongoHistorianThing",
    ["task_insert", "exposed_thing"])


async def _get_aggregated(params_input, motor_client, db_name, query):
    aggr_formats = {
        "second": "%Y_%m_%d_%H_%M_%S",
        "minute": "%Y_%m_%d_%H_%M",
        "hour": "%Y_%m_%d_%H"
    }

    date_format = aggr_formats.get(params_input.get("aggregate"))
    date_format = date_format or aggr_formats["minute"]

    pipeline = [
        {
            "$match": query
        },
        {
            "$addFields": {
                "date_str": {
                    "$dateToString": {
                        "format": date_format,
                        "date": "$utc_date"
                    }
                }
            }
        },
        {
            "$group": {
                "_id": "$date_str",
                "utc_date": {"$last": "$utc_date"},
                "property_name": {"$last": "$property_name"},
                "thing_id": {"$last": "$thing_id"},
                "servient": {"$last": "$servient"},
                "value": {"$last": "$value"}
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
            "thingId": doc.get("thing_id"),
            "propertyName": doc["property_name"],
            "servient": doc.get("servient"),
            "value": doc["value"],
            "isoDate": doc["utc_date"].isoformat()
        }
        async for doc in cur
    ]


async def _get(params, motor_client, db_name):
    params_input = params["input"]

    last_secs = int(params_input.get("lastSeconds", 30))
    gte_date = datetime.utcnow() - datetime.timedelta(seconds=last_secs)

    query = {
        "property_name": {
            "$eq": params_input["propertyName"]
        },
        "utc_date": {
            "$gte": gte_date
        }
    }

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

    if params_input.get("aggregate"):
        return await _get_aggregated(
            params_input=params_input,
            motor_client=motor_client,
            db_name=db_name,
            query=query)

    cur = motor_client[db_name].properties.find(query).sort("utc_date")

    return [
        {
            "thingId": doc.get("thing_id"),
            "propertyName": doc["property_name"],
            "servient": doc.get("servient"),
            "value": doc["value"],
            "isoDate": doc["utc_date"].isoformat()
        }
        async for doc in cur
    ]


async def _write(params, motor_client, db_name):
    params_input = params["input"]
    tstamp = params_input.get("time")
    dtime = datetime.utcfromtimestamp(tstamp) if tstamp else datetime.utcnow()

    result = await motor_client[db_name].properties.insert_one({
        "utc_date": dtime,
        "property_name": params_input["propertyName"],
        "thing_id": params_input.get("thingId"),
        "servient": params_input.get("servient"),
        "value": params_input["value"]
    })

    _logger.debug("Inserted doc %s", result.inserted_id)


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
        ("property_name", pymongo.DESCENDING)
    ]

    _logger.info("Creating index: %s", keys)

    await motor_client[db_name].properties.create_index(
        keys,
        name="utc_date_property_name",
        background=True)


async def _insert_properties(wot, port_catalogue, servient_host, thing_id, motor_client, db_name):
    _logger.debug(
        "Inserting properties (servient=%s) (thing=%s)",
        servient_host, thing_id)

    consumed_thing = await consume_from_catalogue(
        wot=wot,
        port_catalogue=port_catalogue,
        servient_host=servient_host,
        thing_id=thing_id)

    for name in consumed_thing.properties:
        try:
            _logger.debug("Reading property (%s)", name)
            val = await consumed_thing.properties[name].read()
            _logger.debug("Read property (%s=%s)", name, val)
        except Exception as ex:
            _logger.warning("Error reading (%s): %s", name, repr(ex))

        params = {
            "input": {
                "propertyName": name,
                "thingId": thing_id,
                "servient": servient_host,
                "value": val
            }
        }

        await _write(params=params, motor_client=motor_client, db_name=db_name)


async def _start_insert_task(wot, port_catalogue, observed_things, motor_client, db_name, interval):
    _logger.debug(
        "Starting periodic insert task for Things:\n%s",
        pprint.pformat(observed_things))

    insert_props = functools.partial(
        _insert_properties,
        wot=wot,
        port_catalogue=port_catalogue,
        motor_client=motor_client,
        db_name=db_name)

    while True:
        for item in observed_things:
            servient_host = item["servient_host"]
            thing_id = item["thing_id"]

            try:
                await insert_props(servient_host=servient_host, thing_id=thing_id)
            except Exception as ex:
                _logger.warning(
                    "Error inserting properties (servient=%s) (thing=%s): %s",
                    servient_host, thing_id, repr(ex))

        await asyncio.sleep(interval)


async def produce_thing(
        wot, conf, mongo_uri, observed_things, interval,
        db_name=None, timeout_ping=_DEFAULT_TIMEOUT_PING):
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

    try:
        observed_things = observed_things or []
        observed_things = json.loads(observed_things)
    except:
        pass

    async def things_handler():
        return [
            {
                "servient": item["servient_host"],
                "thingId": item["thing_id"]
            }
            for item in observed_things
        ]

    exposed_thing = wot.produce(json.dumps(_DESCRIPTION))
    exposed_thing.set_action_handler("get", handler_get)
    exposed_thing.set_action_handler("write", handler_write)
    exposed_thing.set_property_read_handler("observedThings", things_handler)

    task_insert = asyncio.ensure_future(_start_insert_task(
        wot=wot,
        port_catalogue=conf.port_catalogue,
        observed_things=observed_things,
        motor_client=motor_client,
        db_name=db_name,
        interval=interval))

    return MongoHistorianThing(task_insert=task_insert, exposed_thing=exposed_thing)


async def app(
        wot, conf, loop, mongo_uri, observed_things=None, db_name=None,
        interval=_DEFAULT_INSERT_INTERVAL, timeout_ping=_DEFAULT_TIMEOUT_PING):
    historian_thing = await produce_thing(
        wot=wot,
        conf=conf,
        mongo_uri=mongo_uri,
        observed_things=observed_things,
        interval=interval,
        db_name=db_name,
        timeout_ping=timeout_ping)

    historian_thing.exposed_thing.expose()

    td = ThingDescription.from_thing(historian_thing.exposed_thing.thing)
    _logger.debug("Exposed Thing:\n%s", pprint.pformat(td.to_dict()))
