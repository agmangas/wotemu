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

_QUEUE_MAXSIZE = 5
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


def _detect(queue_item):
    b64_jpg = queue_item["b64_jpg"]
    jpg_bytes = base64.b64decode(b64_jpg)
    frame_arr = cv2.imdecode(np.frombuffer(jpg_bytes, np.uint8), -1)
    return face_recognition.face_locations(frame_arr)


async def _process_queue(detection_queue, store, timeout_get=3.0):
    while True:
        try:
            queue_item = await asyncio.wait_for(detection_queue.get(), timeout_get)
        except asyncio.TimeoutError:
            _logger.debug("Timeout waiting for queue item")
            continue

        b64_jpg = queue_item["b64_jpg"]
        cam_id = queue_item["cam_id"]
        unix_now = queue_item["unix_now"]

        _logger.debug(
            "[%s] Received B64-encoded JPG (%s) (%s KB)",
            cam_id,
            b64_jpg.__class__.__name__,
            round(sys.getsizeof(b64_jpg) / 1024.0, 1))

        loop = asyncio.get_running_loop()
        detect = functools.partial(_detect, queue_item=queue_item)
        face_locations = await loop.run_in_executor(None, detect)
        no_faces = not face_locations or len(face_locations) == 0

        _logger.log(
            logging.DEBUG if no_faces else logging.INFO,
            "[%s] Face locations: %s",
            cam_id, face_locations)

        if no_faces:
            continue

        store_idx = next((
            idx for idx, item in enumerate(store)
            if item["cameraId"] == cam_id), None)

        if store_idx is not None:
            store.pop(store_idx)

        store.append({
            "cameraId": cam_id,
            "jpgB64": b64_jpg,
            "faceLocations": face_locations,
            "unixTime": unix_now
        })


def _on_next(item, cam_id, detection_queue):
    try:
        _logger.debug("Putting new item in detection queue")

        detection_queue.put_nowait({
            "b64_jpg": item.data,
            "unix_now": int(time.time()),
            "cam_id": cam_id
        })
    except asyncio.QueueFull:
        _logger.info("Detection queue is full")


def _on_error(err, cam_id, error_event):
    _logger.warning("[%s] Subscription error: %s", cam_id, err)
    error_event.set()


async def _subscribe_camera(wot, conf, camera, error_event, detection_queue):
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
        detection_queue=detection_queue)

    on_error = functools.partial(
        _on_error,
        cam_id=cam_id,
        error_event=error_event)

    return camera_thing.events[frame_event].subscribe(
        on_next=on_next,
        on_error=on_error)


async def _cancel_subs(subs, cancel_sleep=3):
    _logger.info("Cancelling subscriptions: %s", subs)

    for sub in subs:
        try:
            _logger.debug("Disposing: {}".format(sub))
            sub.dispose()
        except Exception as ex:
            _logger.debug("Error disposing of %s: %s", sub, ex)

    _logger.info("Waiting %s s. for subscriptions", cancel_sleep)
    await asyncio.sleep(cancel_sleep)


async def _subscribe_task(wot, conf, cameras, detection_queue):
    error_event = asyncio.Event()

    while True:
        _logger.info("Clearing error event")
        error_event.clear()

        try:
            _logger.info(
                "Subscribing to cameras:\n%s",
                pprint.pformat(cameras))

            subs = await asyncio.gather(*[
                _subscribe_camera(
                    wot=wot,
                    conf=conf,
                    camera=camera,
                    error_event=error_event,
                    detection_queue=detection_queue)
                for camera in cameras
            ], return_exceptions=False)

            await error_event.wait()
            _logger.warning("Detected error event")
        finally:
            try:
                _cancel_subs(subs)
            except:
                _logger.warning("Error cancelling subs", exc_info=True)


async def _identity(val):
    return val


async def app(wot, conf, loop, cameras):
    cameras = json.loads(cameras)
    detection_queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
    store = list()

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

    await asyncio.gather(
        _process_queue(
            detection_queue=detection_queue,
            store=store),
        _subscribe_task(
            wot=wot,
            conf=conf,
            cameras=cameras,
            detection_queue=detection_queue),
        return_exceptions=False)
