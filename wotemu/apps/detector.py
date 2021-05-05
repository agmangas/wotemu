"""
Video camera aggregator with simple face detection capabilities.
"""

import asyncio
import base64
import functools
import json
import logging
import pprint
import sys

import cv2
import face_recognition
import numpy as np
from wotemu.utils import consume_from_catalogue, wait_node

_DEFAULT_CAMERA_ID = "urn:org:fundacionctic:thing:wotemu:camera"
_DEFAULT_FRAME_EVENT = "jpgVideoFrame"

_DESCRIPTION = {
    "id": "urn:org:fundacionctic:thing:wotemu:detector",
    "name": "Camera detection"
}

_logger = logging.getLogger(__name__)


def _on_next(item, cam_id):
    _logger.debug(
        "[%s] Received B64-encoded JPG (%s) (%s KB)",
        cam_id,
        item.data.__class__.__name__,
        round(sys.getsizeof(item.data) / 1024.0, 1))

    jpg_bytes = base64.b64decode(item.data)
    frame_arr = cv2.imdecode(np.frombuffer(jpg_bytes, np.uint8), -1)

    _logger.debug(
        "[%s] Decoded JPG frame (%s) (%s KB)",
        cam_id,
        frame_arr.__class__.__name__,
        round(sys.getsizeof(frame_arr) / 1024.0, 1))

    face_locations = face_recognition.face_locations(frame_arr)
    _logger.debug("[%s] Face locations: %s", cam_id, face_locations)


def _on_error(err, cam_id, error_event):
    _logger.warning("[%s] Subscription error: %s", cam_id, err)
    error_event.set()


async def _subscribe_camera(wot, conf, camera, error_event):
    servient_host = camera["servient_host"]
    thing_id = camera.get("thing_id", _DEFAULT_CAMERA_ID)
    frame_event = camera.get("frame_event", _DEFAULT_FRAME_EVENT)
    cam_id = f"{servient_host} :: {thing_id}"

    await wait_node(conf=conf, name=servient_host)

    camera_thing = await consume_from_catalogue(
        wot=wot,
        port_catalogue=conf.port_catalogue,
        servient_host=servient_host,
        thing_id=thing_id)

    on_next = functools.partial(_on_next, cam_id=cam_id)

    on_error = functools.partial(
        _on_error,
        cam_id=cam_id,
        error_event=error_event)

    return camera_thing.events[frame_event].subscribe(
        on_next=on_next,
        on_error=on_error)


async def _cancel_subs(subs, cancel_sleep=3):
    for sub in subs:
        try:
            _logger.debug("Disposing: {}".format(sub))
            sub.dispose()
        except Exception as ex:
            _logger.debug("Error disposing of %s: %s", sub, ex)

    _logger.info("Waiting %s s. for subscriptions", cancel_sleep)
    await asyncio.sleep(cancel_sleep)


async def app(wot, conf, loop, cameras):
    cameras = json.loads(cameras)
    error_event = asyncio.Event()

    _logger.info("Subscribing to cameras:\n%s", pprint.pformat(cameras))

    subs = await asyncio.gather(*[
        _subscribe_camera(
            wot=wot,
            conf=conf,
            camera=camera,
            error_event=error_event)
        for camera in cameras
    ], return_exceptions=False)

    _logger.info(
        "Producing Thing:\n%s",
        pprint.pformat(_DESCRIPTION))

    exposed_thing = wot.produce(json.dumps(_DESCRIPTION))
    exposed_thing.expose()

    try:
        await error_event.wait()
    except asyncio.CancelledError:
        _logger.info("Cancelling camera detection app")
    finally:
        await _cancel_subs(subs)
