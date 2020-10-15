import asyncio
import functools
import logging
import pprint
import signal

import sh
from wotemu.monitor.base import NodeMonitor
from wotemu.utils import strip_ansi_codes

_ERR_MOSQUITTO = "error"

_logger = logging.getLogger(__name__)


def _loop_ex_handler(loop, context):
    _logger.warning("Exception in loop:\n%s", pprint.pformat(context))


def _done(cmd, success, exit_code, loop, close_loop):
    _logger.log(
        logging.INFO if success else logging.WARNING,
        "[%s] Exit code: %s",
        cmd.ran,
        exit_code)

    if not success:
        _logger.warning("Mosquitto terminated with error: %s", exit_code)
        asyncio.run_coroutine_threadsafe(close_loop(), loop)


def _out(line):
    line = strip_ansi_codes(line.strip())
    level = logging.WARNING if _ERR_MOSQUITTO in line.lower() else logging.INFO
    _logger.log(level, "[mosquitto] %s", line)


def _run_broker(conf, loop, close_loop):
    sh_mosquitto = sh.Command("mosquitto")

    cmd = [
        "-p",
        f"{conf.port_mqtt}"
    ]

    _logger.info("Running mosquitto: %s", cmd)

    done = functools.partial(
        _done,
        loop=loop,
        close_loop=close_loop)

    proc = sh_mosquitto(
        cmd,
        _err_to_out=True,
        _out=_out,
        _bg=True,
        _done=done)

    return proc


def _terminate_broker(proc):
    try:
        _logger.info("Terminating broker")
        proc.terminate()
        proc.wait()
    except:
        _logger.warning("Error terminating broker", exc_info=True)


async def _close_loop(loop, monitor):
    if monitor:
        try:
            _logger.debug("Stopping monitor")
            await monitor.stop()
        except:
            _logger.warning("Error stopping monitor", exc_info=True)

    _logger.debug("Stopping loop")
    loop.stop()


def _exit_handler(close_loop):
    _logger.debug("Received stop signal")
    asyncio.ensure_future(close_loop())


async def _start_monitor(monitor, close_loop):
    if not monitor:
        return

    try:
        await monitor.start()
    except:
        _logger.warning("Error starting monitor", exc_info=True)
        await close_loop()


def run_mqtt_broker(conf, disable_monitor):
    assert sh.Command("mosquitto")

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(_loop_ex_handler)

    monitor = NodeMonitor(
        redis_url=conf.redis_url) if not disable_monitor else None

    close_loop = functools.partial(
        _close_loop,
        loop=loop,
        monitor=monitor)

    exit_handler = functools.partial(
        _exit_handler,
        close_loop=close_loop)

    start_monitor = functools.partial(
        _start_monitor,
        monitor=monitor,
        close_loop=close_loop)

    for name in {"SIGINT", "SIGTERM"}:
        loop.add_signal_handler(getattr(signal, name), exit_handler)

    proc = None

    try:
        asyncio.ensure_future(start_monitor())
        proc = _run_broker(conf=conf, loop=loop, close_loop=close_loop)
        _logger.debug("Running loop")
        loop.run_forever()
    finally:
        _logger.debug("Closing loop")
        loop.close()
        _terminate_broker(proc=proc)
