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
import time

import cv2
import face_recognition
import numpy as np
from wotemu.utils import consume_from_catalogue, wait_node
from wotpy.wot.td import ThingDescription

_DEFAULT_CAMERA_ID = "urn:org:fundacionctic:thing:wotemu:camera"
_DEFAULT_FRAME_EVENT = "jpgVideoFrame"

_DESCRIPTION = {
    "id": "urn:org:fundacionctic:thing:wotemu:detector",
    "name": "Camera detection",
    "properties": {
        "cameras": {
            "readOnly": True,
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "servient_host": {
                        "type": "string"
                    },
                    "thing_id": {
                        "type": "string"
                    },
                    "frame_event": {
                        "type": "string"
                    }
                },
                "required": ["servient_host"]
            }
        },
        "latestDetections": {
            "readOnly": True,
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cameraId": {
                        "type": "string"
                    },
                    "jpgB64": {
                        "type": "string"
                    },
                    "faceLocations": {
                        "type": "array"
                    },
                    "unixTime": {
                        "type": "number"
                    }
                },
                "required": ["cameraId", "jpgB64", "faceLocations", "unixTime"]
            }
        }
    }
}

_logger = logging.getLogger(__name__)


def _on_next(item, cam_id, store):
    unix_now = int(time.time())
    b64_jpg = item.data

    _logger.debug(
        "[%s] Received B64-encoded JPG (%s) (%s KB)",
        cam_id,
        b64_jpg.__class__.__name__,
        round(sys.getsizeof(b64_jpg) / 1024.0, 1))

    jpg_bytes = base64.b64decode(b64_jpg)
    frame_arr = cv2.imdecode(np.frombuffer(jpg_bytes, np.uint8), -1)

    _logger.debug(
        "[%s] Decoded JPG frame (%s) (%s KB)",
        cam_id,
        frame_arr.__class__.__name__,
        round(sys.getsizeof(frame_arr) / 1024.0, 1))

    face_locations = face_recognition.face_locations(frame_arr)

    if not face_locations or len(face_locations) == 0:
        return

    _logger.info("[%s] Face locations: %s", cam_id, face_locations)

    store_idx = next(
        (idx for idx, item in enumerate(store) if item["cameraId"] == cam_id),
        None)

    if store_idx is not None:
        store.pop(store_idx)

    store.append({
        "cameraId": cam_id,
        "jpgB64": b64_jpg,
        "faceLocations": face_locations,
        "unixTime": unix_now
    })


def _on_error(err, cam_id, error_event):
    _logger.warning("[%s] Subscription error: %s", cam_id, err)
    error_event.set()


async def _subscribe_camera(wot, conf, camera, error_event, store):
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

    on_next = functools.partial(
        _on_next,
        cam_id=cam_id,
        store=store)

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


async def _identity(val):
    return val


async def app(wot, conf, loop, cameras):
    cameras = json.loads(cameras)
    error_event = asyncio.Event()
    store = list()

    _logger.info("Subscribing to cameras:\n%s", pprint.pformat(cameras))

    subs = await asyncio.gather(*[
        _subscribe_camera(
            wot=wot,
            conf=conf,
            camera=camera,
            error_event=error_event,
            store=store)
        for camera in cameras
    ], return_exceptions=False)

    _logger.info(
        "Producing Thing:\n%s",
        pprint.pformat(_DESCRIPTION))

    exposed_thing = wot.produce(json.dumps(_DESCRIPTION))

    exposed_thing.set_property_read_handler(
        "cameras",
        functools.partial(_identity, val=cameras))

    exposed_thing.set_property_read_handler(
        "latestDetections",
        functools.partial(_identity, val=store))

    exposed_thing.expose()

    _logger.debug(
        "Exposed Thing:\n%s",
        pprint.pformat(ThingDescription.from_thing(exposed_thing.thing).to_dict()))

    try:
        await error_event.wait()
    except asyncio.CancelledError:
        _logger.info("Cancelling camera detection app")
    finally:
        await _cancel_subs(subs)
