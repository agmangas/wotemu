import asyncio
import functools
import logging
import multiprocessing
import os
import queue
import time

import pyshark
from pyshark.capture.capture import StopCapture

_logger = logging.getLogger(__name__)


def _build_display_filter(conf):
    return (
        "tcp.port=={port_mqtt} or "
        "tcp.port=={port_http} or "
        "tcp.port=={port_ws} or "
        "tcp.port=={port_coap} or "
        "udp.port=={port_coap}"
    ).format(
        port_http=conf.port_http,
        port_ws=conf.port_ws,
        port_mqtt=conf.port_mqtt,
        port_coap=conf.port_coap)


def _packet_to_dict(packet):
    ret = {
        "len": int(packet.length),
        "src": packet.ip.src,
        "dst": packet.ip.dst,
        "proto": packet.layers[-1].layer_name,
        "transport": packet.layers[2].layer_name,
        "time": float(packet.sniff_timestamp)
    }

    try:
        ret.update({
            "srcport": int(packet.tcp.srcport),
            "dstport": int(packet.tcp.dstport)
        })
    except AttributeError:
        pass

    try:
        ret.update({
            "srcport": int(packet.udp.srcport),
            "dstport": int(packet.udp.dstport)
        })
    except AttributeError:
        pass

    return ret


def _packet_callback(packet, output_queue, stop_event):
    packet_dict = _packet_to_dict(packet)
    output_queue.put(packet_dict)

    if stop_event.is_set():
        raise StopCapture()


def _start_capture(display_filter, interface, output_queue, stop_event):
    capture = pyshark.LiveCapture(
        interface=interface,
        only_summaries=False,
        display_filter=display_filter)

    on_packet = functools.partial(
        _packet_callback,
        output_queue=output_queue,
        stop_event=stop_event)

    capture.apply_on_packets(on_packet)


def _read_queue(output_queue, queue_size):
    counter = 0
    ret = []

    try:
        while not output_queue.empty():
            item = output_queue.get_nowait()
            ret.append(item)
            counter += 1
            if counter > queue_size:
                break
    except queue.Empty:
        pass

    return ret


def _check_proc_alive(proc):
    if not proc.is_alive() or proc.exitcode is not None:
        err_msg = (
            "Tshark packet capture process "
            "stopped prematurely "
            "(exit code: {})"
        ).format(proc.exitcode)

        raise RuntimeError(err_msg)


async def _terminate_proc(proc, stop_event, stop_sleep=2, stop_timeout=10, join_timeout=5):
    _logger.debug("Setting Tshark process stop event")
    stop_event.set()

    _logger.debug("Waiting %s seconds for Tshark process", stop_timeout)
    time_limit = time.time() + stop_timeout

    while time.time() <= time_limit:
        if proc.exitcode is not None:
            break
        await asyncio.sleep(stop_sleep)

    if proc.exitcode is not None:
        _logger.debug("Tshark process exited with code: %s", proc.exitcode)
        return

    _logger.warning("Tshark process did not terminate with stop event")

    try:
        _logger.info("Terminating process: %s", proc)
        proc.terminate()
        proc.join(join_timeout)
    except:
        _logger.warning("Error terminating", exc_info=True)
    finally:
        try:
            if proc.exitcode is None:
                _logger.warning("Killing process: %s", proc)
                proc.kill()
        except:
            _logger.warning("Error killing", exc_info=True)


async def monitor_packets(conf, interface, async_cb, queue_size=30, sleep=2.0, terminate_kwargs=None):
    spawn_ctx = multiprocessing.get_context("spawn")
    display_filter = _build_display_filter(conf=conf)
    output_queue = spawn_ctx.Queue(queue_size)
    stop_event = spawn_ctx.Event()

    proc_target = functools.partial(
        _start_capture,
        display_filter=display_filter,
        interface=interface,
        output_queue=output_queue,
        stop_event=stop_event)

    _logger.debug(
        "Starting LiveCapture on interface %s with display filter: %s",
        interface,
        display_filter)

    proc = spawn_ctx.Process(target=proc_target, daemon=True)
    proc.start()

    read_output_queue = functools.partial(
        _read_queue,
        output_queue=output_queue,
        queue_size=queue_size)

    check_proc_health = functools.partial(
        _check_proc_alive,
        proc=proc)

    terminate_kwargs = terminate_kwargs if terminate_kwargs else {}

    terminate_process = functools.partial(
        _terminate_proc,
        proc=proc,
        stop_event=stop_event,
        **terminate_kwargs)

    try:
        while True:
            items = read_output_queue()
            if items and len(items) > 0:
                await async_cb(items)
            check_proc_health()
            await asyncio.sleep(sleep)
    except asyncio.CancelledError:
        _logger.debug("Cancelled Tshark capture task")
    finally:
        if proc.exitcode is None:
            await terminate_process()
