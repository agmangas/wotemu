"""
Mock video camera with naive motion detection capabilities.
"""

import asyncio
import base64
import collections
import importlib.resources
import json
import logging
import pprint
import random
import sys
import time

import cv2
import numpy as np
from wotemu.monitor.utils import write_metric
from wotpy.wot.td import ThingDescription

_VIDEO_PKG = "wotemu.apps.data"
_VIDEO_RESOURCE = "camera.mp4"
_MOTION_THRESHOLD = 25.0
_JPEG_QUALITY = 60
_PTZ_MU = 0.0
_PTZ_SIGMA = 1.0
_PTZ_LOOP_SLEEP = 0.1
_METRIC_PTZ_LATENCY = "ptz_latency"


_DESCRIPTION = {
    "id": "urn:org:fundacionctic:thing:wotemu:camera",
    "name": "Mock video camera",
    "actions": {
        "controlPTZ": {
            "safe": True,
            "idempotent": False,
            "input": {
                "type": "object"
            }
        }
    },
    "events": {
        "jpgVideoFrame": {
            "data": {
                "type": "object"
            }
        }
    }
}

_logger = logging.getLogger(__name__)


def _get_video_path():
    with importlib.resources.path(_VIDEO_PKG, _VIDEO_RESOURCE) as pth:
        return str(pth)


def _frames_generator():
    video_path = _get_video_path()

    try:
        _logger.info("Initializing cv2.VideoCapture: %s", video_path)
        cap = cv2.VideoCapture(video_path)
        frame_counter = 0

        while cap.isOpened():
            ret, frame = cap.read()
            frame_counter += 1

            if not ret:
                raise RuntimeError("Error reading video frame")

            if frame_counter == cap.get(cv2.CAP_PROP_FRAME_COUNT):
                _logger.debug("Resetting cv2.CAP_PROP_POS_FRAMES")
                frame_counter = 0
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

            yield frame
    finally:
        try:
            cap.release()
        except:
            _logger.warning("Error releasing capture", exc_info=True)


def _get_motion_score(frames):
    frames_grey = [cv2.cvtColor(item, cv2.COLOR_BGR2GRAY) for item in frames]
    frames_flat = [item.flatten() for item in frames_grey]
    diff_arr = np.diff(frames_flat, axis=0)
    means_arr = [abs(np.mean(item)) for item in diff_arr]
    return np.mean(means_arr)


async def _video_motion_generator(target_fps=12, buf_size=None, motion_threshold=None):
    buf_size = buf_size or int(target_fps)
    motion_threshold = motion_threshold or _MOTION_THRESHOLD
    frames_buf = collections.deque([], buf_size)
    frame_sleep = 1.0 / float(target_fps)

    for frame in _frames_generator():
        frames_buf.append(frame)
        motion_score = _get_motion_score(frames_buf)
        yield frame, motion_score > motion_threshold
        await asyncio.sleep(frame_sleep)


def _to_b64_jpg(frame):
    params = [cv2.IMWRITE_JPEG_QUALITY, _JPEG_QUALITY]
    retval, img_bytes = cv2.imencode(".jpg", frame, params)
    assert retval
    return base64.b64encode(img_bytes).decode()


async def _video_frame_emitter(exposed_thing):
    async for frame, motion in _video_motion_generator():
        if motion:
            frame_jpg = _to_b64_jpg(frame)
            frame_kb = round(sys.getsizeof(frame_jpg) / 1024.0, 1)
            _logger.debug("Emitting jpgVideoFrame (%s KB)", frame_kb)
            assert isinstance(frame_jpg, str)

            exposed_thing.emit_event("jpgVideoFrame", {
                "time_capture": time.time(),
                "b64_jpg": frame_jpg
            })


async def _control_ptz(params):
    params_input = params["input"]
    params_input = params_input or {}

    if params_input.get("time_capture"):
        latency_ptz = time.time() - float(params_input["time_capture"])
        data = {"latency_ptz": latency_ptz}
        data.update(params_input)
        await write_metric(key=_METRIC_PTZ_LATENCY, data=data)

    sleep_secs = abs(random.gauss(_PTZ_MU, _PTZ_SIGMA))
    sleep_end = time.time() + sleep_secs

    while time.time() < sleep_end:
        await asyncio.sleep(_PTZ_LOOP_SLEEP)


async def app(wot, conf, loop):
    _logger.info("Starting mock video camera app")

    _logger.info(
        "Producing Thing:\n%s",
        pprint.pformat(_DESCRIPTION))

    exposed_thing = wot.produce(json.dumps(_DESCRIPTION))
    exposed_thing.set_action_handler("controlPTZ", _control_ptz)
    exposed_thing.expose()

    _logger.debug(
        "Exposed Thing:\n%s",
        pprint.pformat(ThingDescription.from_thing(exposed_thing.thing).to_dict()))

    await _video_frame_emitter(exposed_thing=exposed_thing)
