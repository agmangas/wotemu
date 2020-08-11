import logging
import pprint
import re
import signal
import time

import docker
import netifaces
import sh

from wotemu.utils import (get_current_container_id, ping_docker,
                          strip_ansi_codes)

_IFACE_LO = "lo"
_LEVEL_DEBUG = "DEBU["
_LEVEL_INFO = "INFO["

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
        raise Exception("Could not find chaos network interface")

    return candidates[0]


def _pumba_log_level(line):
    if line.startswith(_LEVEL_DEBUG):
        return logging.DEBUG
    elif line.startswith(_LEVEL_INFO):
        return logging.INFO
    else:
        return logging.WARNING


def _build_out(cmd_id):
    def out(line):
        line = strip_ansi_codes(line.strip())
        _logger.log(_pumba_log_level(line), "[%s]\n\t%s", cmd_id, line.strip())

    return out


def _done(cmd, success, exit_code):
    _logger.log(
        logging.INFO if success else logging.WARNING,
        "[%s] Exit code: %s",
        cmd.ran,
        exit_code)


def create_chaos(conf, docker_url, netem, duration):
    ping_docker(docker_url=docker_url)

    docker_client = docker.DockerClient(base_url=docker_url)
    cid = get_current_container_id()
    container = docker_client.containers.get(cid)

    cmd_base = "--host {} --log-level debug netem --duration {} --interface {}".format(
        docker_url,
        duration,
        _find_chaos_interface())

    cmds = [
        "{} {} {}".format(cmd_base, netem_cmd, container.name)
        for netem_cmd in netem
    ]

    _logger.info("Running Pumba commands:\n%s", pprint.pformat(cmds))

    sh_pumba = sh.Command("pumba")

    procs = [
        sh_pumba(
            cmd.split(),
            _err_to_out=True,
            _out=_build_out(cmd_id=netem[idx]),
            _bg=True,
            _done=_done)
        for idx, cmd in enumerate(cmds)
    ]

    def exit_handler(signum, frame):
        _logger.info("Terminating Pumba processes")
        [proc.terminate() for proc in procs]

    signal.signal(signal.SIGINT, exit_handler)
    signal.signal(signal.SIGTERM, exit_handler)

    _logger.debug("Waiting for Pumba processes")
    [proc.wait() for proc in procs]
