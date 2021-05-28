import json
import logging
import shlex
import signal
import subprocess
import time

import netifaces

_IFACE_LO = "lo"

_logger = logging.getLogger(__name__)


def _find_chaos_interface():
    # Chaos commands are meant to be run in a "gateway" container.
    # These are attached to a single network, and thus there is only one interface.

    gws = netifaces.gateways()
    gw_default = gws.get("default", None)
    gw_iface = gw_default[netifaces.AF_INET][1] if gw_default else None

    if gw_iface:
        _logger.debug("Default gateway interface: %s", gw_iface)
    else:
        _logger.warning("Could not find gateway interface")

    candidates = [
        iface for iface in netifaces.interfaces()
        if iface not in [_IFACE_LO, gw_iface]
    ]

    if len(candidates) > 1:
        _logger.warning("More than 1 candidate interface: %s", candidates)

    if len(candidates) == 0:
        raise RuntimeError("Could not find chaos network interface")

    return candidates[0]


def _call(command):
    _logger.debug("call: %s", command)
    subprocess.call(shlex.split(command))


def _check_call(command):
    _logger.debug("check_call: %s", command)
    subprocess.check_call(shlex.split(command))


def _clean_netem(nic):
    _logger.info("Undoing netem configuration")
    _call(f"tc qdisc del dev {nic} root")


_DEFAULT_DELAY_CORR = 0
_DEFAULT_RATE_BURST = "100kbit"
_DEFAULT_RATE_LATENCY = 20
_QDISC_PARENT = "root handle 1:"
_QDISC_CHILD = "parent 1: handle 2:"


def _set_delay(nic, latency, jitter, corr=None, root=True):
    # See: https://man7.org/linux/man-pages/man8/tc-netem.8.html
    # See: https://www.excentis.com/blog/use-linux-traffic-control-impairment-node-test-environment-part-1

    corr = _DEFAULT_DELAY_CORR if corr is None else corr
    qdiscs = _QDISC_PARENT if root else _QDISC_CHILD

    cmd = (
        "tc qdisc add dev {} {} "
        "netem delay {}ms {}ms {}% distribution normal"
    ).format(nic, qdiscs, latency, jitter, corr)

    _check_call(cmd)


def _set_rate(nic, rate, burst=None, latency=None, root=False):
    # See: https://man7.org/linux/man-pages/man8/tc-tbf.8.html

    burst = _DEFAULT_RATE_BURST if burst is None else burst
    latency = _DEFAULT_RATE_LATENCY if latency is None else latency
    qdiscs = _QDISC_PARENT if root else _QDISC_CHILD

    cmd = (
        "tc qdisc add dev {} {} "
        "tbf rate {} burst {} latency {}ms"
    ).format(nic, qdiscs, rate, burst, latency)

    _check_call(cmd)


_ITER_SLEEP_SECS = 1.0


def create_chaos(conf, netem):
    nic = _find_chaos_interface()
    _logger.info("Found chaos interface: %s", nic)

    assert len(netem) == 1, "Unexpected number of netem argument items"
    netem_args = json.loads(netem[0])
    _logger.info("Imposing netem constraints: %s", netem_args)

    def exit_handler(*_):
        _clean_netem(nic=nic)
        exit(0)

    signal.signal(signal.SIGINT, exit_handler)
    signal.signal(signal.SIGTERM, exit_handler)

    _clean_netem(nic=nic)

    delay_defined = netem_args.get("latency") is not None \
        and netem_args.get("jitter") is not None

    if delay_defined:
        _set_delay(
            nic=nic,
            latency=netem_args["latency"],
            jitter=netem_args["jitter"],
            corr=netem_args.get("correlation"),
            root=True)

    if netem_args.get("rate") is not None:
        _set_rate(
            nic=nic,
            rate=netem_args["rate"],
            burst=netem_args.get("rate_burst"),
            latency=netem_args.get("rate_latency"),
            root=not delay_defined)

    try:
        _logger.info("Sleeping indefinitely")

        while True:
            time.sleep(_ITER_SLEEP_SECS)
    finally:
        _clean_netem(nic=nic)
