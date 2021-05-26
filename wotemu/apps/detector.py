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
from wotemu.monitor.utils import write_metric
from wotemu.utils import consume_from_catalogue, wait_node
from wotpy.wot.td import ThingDescription

_QUEUE_MAXSIZE = 50
_QUEUE_MAX_SECONDS = 10
_DEFAULT_CAMERA_ID = "urn:org:fundacionctic:thing:wotemu:camera"
_DEFAULT_FRAME_EVENT = "jpgVideoFrame"
_PTZ_ACTION = "controlPTZ"
_METRIC_LATENCY = "detection_latency"

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


async def _control_camera_ptz(wot, conf, camera_id, lock, **kwargs):
    try:
        await lock.acquire()

        _logger.debug("Invoking PTZ control: %s", camera_id)

        splitted = camera_id.split("::")
        servient_host = splitted[0].strip()
        thing_id = splitted[1].strip()

        camera_thing = await consume_from_catalogue(
            wot=wot,
            port_catalogue=conf.port_catalogue,
            servient_host=servient_host,
            thing_id=thing_id)

        await camera_thing.actions[_PTZ_ACTION].invoke(kwargs)

        _logger.debug("Finished PTZ control invocation: %s", camera_id)
    except Exception as ex:
        _logger.warning("Failed updating PTZ controls: %s", repr(ex))
    finally:
        lock.release()


async def _process_queue(wot, conf, detection_queue, store, counters, timeout_get=3.0):
    locks = {}

    while True:
        try:
            _, queue_item = await asyncio.wait_for(detection_queue.get(), timeout_get)
        except asyncio.TimeoutError:
            _logger.debug("Timeout waiting for queue item")
            continue

        b64_jpg = queue_item["b64_jpg"]
        cam_id = queue_item["cam_id"]
        time_arrival = queue_item["time_arrival"]
        time_capture = queue_item["time_capture"]

        if (time.time() - time_arrival) >= _QUEUE_MAX_SECONDS:
            _logger.info("Dropping old item (>%s s.)", _QUEUE_MAX_SECONDS)
            continue

        _logger.debug(
            "[%s] Received B64-encoded JPG (%s) (%s KB)",
            cam_id,
            b64_jpg.__class__.__name__,
            round(sys.getsizeof(b64_jpg) / 1024.0, 1))

        time_pre_detect = time.time()

        loop = asyncio.get_running_loop()
        detect = functools.partial(_detect, queue_item=queue_item)
        face_locations = await loop.run_in_executor(None, detect)
        no_faces = not face_locations or len(face_locations) == 0

        time_detect = time.time()

        _logger.log(
            logging.DEBUG if no_faces else logging.INFO,
            "[%s] Face locations: %s",
            cam_id, face_locations)

        await write_metric(key=_METRIC_LATENCY, data={
            "time_capture": time_capture,
            "time_arrival": time_arrival,
            "time_detect": time_detect,
            "latency_frame": time_arrival - time_capture,
            "latency_detect": time_detect - time_arrival,
            "detect_cost": time_detect - time_pre_detect,
            "camera_id": cam_id
        })

        counters[cam_id] = counters.get(cam_id, 0) + 1
        _logger.debug("Current frame counters: %s", counters)

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
            "unixTime": time_capture
        })

        if not locks.get(cam_id):
            _logger.debug("Initializing lock for %s", cam_id)
            locks[cam_id] = asyncio.Lock()

        lock = locks[cam_id]

        if lock.locked():
            _logger.debug("Skipping PTZ control for %s", cam_id)
            continue

        asyncio.ensure_future(_control_camera_ptz(
            wot=wot,
            conf=conf,
            camera_id=cam_id,
            lock=lock,
            time_capture=time_capture,
            time_arrival=time_arrival,
            time_detect=time_detect))


def _frame_priority(cam_id, time_capture, counters):
    age = float(time.time() - time_capture)
    cam_count = counters.get(cam_id, 0)
    return cam_count + (1.0 / age)


def _on_next(item, cam_id, detection_queue, counters):
    try:
        _logger.debug("Putting new item in detection queue")

        time_capture = item.data["time_capture"]
        item_prio = _frame_priority(cam_id, time_capture, counters)

        item_data = {
            "b64_jpg": item.data["b64_jpg"],
            "time_capture": time_capture,
            "time_arrival": time.time(),
            "cam_id": cam_id
        }

        detection_queue.put_nowait((item_prio, item_data))
    except asyncio.QueueFull:
        _logger.info("Detection queue is full")


def _on_error(err, cam_id, error_event):
    _logger.warning("[%s] Subscription error: %s", cam_id, err)
    error_event.set()


async def _subscribe_camera(wot, conf, camera, error_event, detection_queue, counters):
    servient_host = camera["servient_host"]
    thing_id = camera.get("thing_id", _DEFAULT_CAMERA_ID)
    frame_event = camera.get("frame_event", _DEFAULT_FRAME_EVENT)
    cam_id = f"{servient_host} :: {thing_id}"

    await wait_node(conf=conf, name=servient_host, thing_ids=[thing_id])

    camera_thing = await consume_from_catalogue(
        wot=wot,
        port_catalogue=conf.port_catalogue,
        servient_host=servient_host,
        thing_id=thing_id)

    on_next = functools.partial(
        _on_next,
        cam_id=cam_id,
        detection_queue=detection_queue,
        counters=counters)

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


async def _subscribe_task(wot, conf, cameras, detection_queue, counters):
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
                    detection_queue=detection_queue,
                    counters=counters)
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


async def app(wot, conf, loop, cameras, queue_maxsize=_QUEUE_MAXSIZE):
    store = list()
    cameras = json.loads(cameras)
    counters = dict()
    detection_queue = asyncio.PriorityQueue(maxsize=queue_maxsize)

    _logger.info(
        "Producing Thing:\n%s",
        pprint.pformat(_DESCRIPTION))

    exposed_thing = wot.produce(json.dumps(_DESCRIPTION))

    exposed_thing.set_property_read_handler(
        "latestDetections",
        functools.partial(_identity, val=store))

    exposed_thing.set_property_read_handler(
        "cameras",
        functools.partial(_identity, val=cameras))

    exposed_thing.expose()

    _logger.debug(
        "Exposed Thing:\n%s",
        pprint.pformat(ThingDescription.from_thing(exposed_thing.thing).to_dict()))

    await asyncio.gather(
        _process_queue(
            wot=wot,
            conf=conf,
            detection_queue=detection_queue,
            store=store,
            counters=counters),
        _subscribe_task(
            wot=wot,
            conf=conf,
            cameras=cameras,
            detection_queue=detection_queue,
            counters=counters),
        return_exceptions=False)
