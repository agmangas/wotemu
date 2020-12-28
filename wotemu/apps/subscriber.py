import asyncio
import functools
import json
import logging
import pprint
import sys

import tornado.httpclient
from wotemu.utils import consume_from_catalogue, wait_node

_logger = logging.getLogger(__name__)


def _on_next(item, interaction):
    _logger.info("%s: Next\n%s", interaction, item)


def _on_completed(interaction):
    _logger.info("%s: Completed", interaction)


def _on_error(err, interaction, error_event):
    _logger.warning("%s: Error\n%s", interaction, err)
    error_event.set()


def _subscribe(interaction, error_event):
    _logger.debug("Subscribing to: {}".format(interaction))

    return interaction.subscribe(
        on_next=functools.partial(_on_next, interaction=interaction),
        on_completed=functools.partial(_on_completed, interaction=interaction),
        on_error=functools.partial(_on_error, interaction=interaction, error_event=error_event))


async def _cancel_subs(subs, cancel_sleep=3):
    for sub in subs:
        try:
            _logger.debug("Disposing: {}".format(sub))
            sub.dispose()
        except Exception as ex:
            _logger.debug("Error disposing of %s: %s", sub, ex)

    _logger.info("Waiting %s s. for subscriptions", cancel_sleep)
    await asyncio.sleep(cancel_sleep)


async def _consume_and_subscribe(wot, conf, servient_host, thing_id, error_event):
    await wait_node(conf=conf, name=servient_host)

    consumed_thing = await consume_from_catalogue(
        wot=wot,
        port_catalogue=conf.port_catalogue,
        servient_host=servient_host,
        thing_id=thing_id)

    subs = []

    for name in consumed_thing.properties:
        if consumed_thing.properties[name].observable:
            sub = _subscribe(consumed_thing.properties[name], error_event)
            subs.append(sub)

    for name in consumed_thing.events:
        sub = _subscribe(consumed_thing.events[name], error_event)
        subs.append(sub)

    return subs


async def app(wot, conf, loop, servient_host, thing_id):
    error_event = asyncio.Event()

    consume_subscribe_partial = functools.partial(
        _consume_and_subscribe,
        wot=wot,
        conf=conf,
        servient_host=servient_host,
        thing_id=thing_id,
        error_event=error_event)

    try:
        while True:
            subs = await consume_subscribe_partial()
            await error_event.wait()
            _cancel_subs(subs)
            error_event.clear()
    except asyncio.CancelledError:
        await _cancel_subs(subs)
