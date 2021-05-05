"""
Mock video camera with naive motion detection capabilities.
"""

import asyncio
import base64
import collections
import functools
import importlib.resources
import io
import json
import logging
import pprint

import cv2
import numpy as np
from wotpy.wot.td import ThingDescription

_VIDEO_PKG = "wotemu.apps.data"
_VIDEO_RESOURCE = "camera.mp4"
_MOTION_THRESHOLD = 25.0
_TIMEOUT = 10

_DESCRIPTION = {
    "id": "urn:org:fundacionctic:thing:wotemu:camera",
    "name": "Mock video camera",
    "events": {
        "jpgVideoFrame": {
            "data": {
                "type": "string"
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
    except asyncio.CancelledError:
        _logger.info("Cancelled video generator")
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


def _to_jpg_str(frame):
    retval, img_bytes = cv2.imencode(".jpg", frame)
    assert retval
    return base64.b64encode(img_bytes).decode()


async def _video_frame_emitter(exposed_thing):
    async for frame, motion in _video_motion_generator():
        if motion:
            str_frame = _to_jpg_str(frame)
            _logger.debug("Emitting video frame")
            exposed_thing.emit_event("jpgVideoFrame", str_frame)
        else:
            _logger.debug("Dropping frame")


async def app(wot, conf, loop):
    _logger.info("Starting mock video camera app")

    _logger.info(
        "Producing Thing:\n%s",
        pprint.pformat(_DESCRIPTION))

    exposed_thing = wot.produce(json.dumps(_DESCRIPTION))
    exposed_thing.expose()

    _logger.debug(
        "Exposed Thing:\n%s",
        pprint.pformat(ThingDescription.from_thing(exposed_thing.thing).to_dict()))

    video_frame_emitter = functools.partial(
        _video_frame_emitter,
        exposed_thing=exposed_thing)

    video_frame_task = asyncio.ensure_future(video_frame_emitter())

    try:
        await video_frame_task
    except asyncio.CancelledError:
        await asyncio.wait_for(video_frame_task, _TIMEOUT)
