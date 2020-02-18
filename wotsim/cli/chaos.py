import logging
import pprint
import re
import signal
import time

import docker
import netifaces
import sh

import wotsim.cli.utils

_IFACE_LO = "lo"
_LEVEL_DEBUG = "DEBU["
_LEVEL_INFO = "INFO["

_logger = logging.getLogger(__name__)


def _find_chaos_interface():
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


def create_chaos(docker_url, netem, duration):
    wotsim.cli.utils.ping_docker(docker_url=docker_url)

    docker_client = docker.DockerClient(base_url=docker_url)
    cid = wotsim.cli.utils.current_container_id()
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

    def build_out(idx):
        def out(line):
            line = wotsim.cli.utils.strip_ansi_codes(line.strip())
            level = logging.WARNING

            if line.startswith(_LEVEL_DEBUG):
                level = logging.DEBUG
            elif line.startswith(_LEVEL_INFO):
                level = logging.INFO

            _logger.log(level, "[%s]\n\t%s", netem[idx], line)

        return out

    def done(cmd, success, exit_code):
        _logger.log(
            logging.INFO if success else logging.WARNING,
            "[%s] Exit code: %s", cmd.ran, exit_code)

    sh_pumba = sh.Command("pumba")

    procs = [
        sh_pumba(
            cmd.split(),
            _err_to_out=True,
            _out=build_out(idx=idx),
            _bg=True,
            _done=done)
        for idx, cmd in enumerate(cmds)
    ]

    def exit_handler(signum, frame):
        _logger.info("Terminating Pumba processes")
        [proc.terminate() for proc in procs]

    signal.signal(signal.SIGINT, exit_handler)
    signal.signal(signal.SIGTERM, exit_handler)

    _logger.debug("Waiting for Pumba processes")
    [proc.wait() for proc in procs]
