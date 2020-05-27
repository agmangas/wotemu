import asyncio
import functools
import json
import logging
import pprint
import sys

import tornado.httpclient

_CANCEL_SLEEP = 3

_logger = logging.getLogger("wotsim.subscriber.app")


async def _consume_from_catalogue(wot, port_catalogue, servient_host, thing_id):
    http_client = tornado.httpclient.AsyncHTTPClient()
    catalogue_url = "http://{}:{}".format(servient_host, port_catalogue)

    _logger.debug("Fetching catalogue: %s", catalogue_url)

    catalogue_res = await http_client.fetch(catalogue_url)
    catalogue = json.loads(catalogue_res.body)

    _logger.debug("Catalogue:\n%s", pprint.pformat(catalogue))

    if thing_id not in catalogue:
        raise Exception(
            "Thing '{}' not found in catalogue: {}".format(thing_id, catalogue_url))

    td_url = "http://{}:{}/{}".format(
        servient_host,
        port_catalogue,
        catalogue[thing_id].strip("/"))

    _logger.debug("Consuming from URL: %s", td_url)

    return await wot.consume_from_url(td_url)


def _on_next(item, interaction):
    _logger.info("%s: Next\n%s", interaction, item)


def _on_completed(interaction):
    _logger.info("%s: Completed", interaction)


def _on_error(err, interaction):
    _logger.warning("%s: Error\n%s", interaction, err)


def _subscribe(interaction):
    _logger.debug("Subscribing to: {}".format(interaction))

    return interaction.subscribe(
        on_next=functools.partial(_on_next, interaction=interaction),
        on_completed=functools.partial(_on_completed, interaction=interaction),
        on_error=functools.partial(_on_error, interaction=interaction))


async def _cancel_subs(subs):
    for sub in subs:
        _logger.debug("Disposing: {}".format(sub))
        sub.dispose()

    _logger.info("Waiting for subscriptions")
    await asyncio.sleep(_CANCEL_SLEEP)


async def app(wot, conf, loop, servient_host, thing_id):
    consumed_thing = await _consume_from_catalogue(
        wot=wot,
        port_catalogue=conf.port_catalogue,
        servient_host=servient_host,
        thing_id=thing_id)

    subs = []

    for name in consumed_thing.properties:
        if consumed_thing.properties[name].observable:
            subs.append(_subscribe(consumed_thing.properties[name]))

    for name in consumed_thing.events:
        subs.append(_subscribe(consumed_thing.events[name]))

    try:
        await asyncio.sleep(sys.maxsize)
    except asyncio.CancelledError:
        await _cancel_subs(subs)
