import logging
import pprint
import re
import warnings

import docker
import numpy

_SYSBENCH_IMAGE = "severalnines/sysbench"
_SYSBENCH_THREADS = 1
_SYSBENCH_TIME = 10
_CPU_PERIOD = 100000
_REGEX_SPEED = r"events\sper\ssecond:\s*(\d+\.\d+)"
_CPU_SAMPLES_NUM = 6
_CPU_SAMPLES_START = 0.1
_CPU_SAMPLES_STOP = 1.0
_CACHE_POLY = "poly"

assert _CPU_SAMPLES_START > 0

_cache = {_CACHE_POLY: None}
_logger = logging.getLogger(__name__)


def get_cpu_core_speed(cpus):
    client = docker.from_env()

    command = "sysbench --threads={} --time={} cpu run".format(
        _SYSBENCH_THREADS,
        _SYSBENCH_TIME)

    cpu_quota = int(_CPU_PERIOD * cpus)

    _logger.info("Running for [cpus=%s]: %s", cpus, command)

    output = client.containers.run(
        remove=True,
        image=_SYSBENCH_IMAGE,
        command=command,
        cpu_period=_CPU_PERIOD,
        cpu_quota=cpu_quota)

    output = output.decode()

    _logger.debug("[cpus=%s] %s\n%s", cpus, command, output)

    speed_match = re.search(_REGEX_SPEED, output)

    if len(speed_match.groups()) != 1:
        raise Exception("CPU speed not found in sysbench output")

    cpu_speed = float(speed_match.group(1))

    _logger.debug("CPU speed: %s", cpu_speed)

    return cpu_speed


def get_cpu_core_speed_poly(cache=True):
    if cache and _cache.get(_CACHE_POLY):
        _logger.debug("Using cached CPU core speed poly")
        return _cache.get(_CACHE_POLY)

    _logger.info("Building CPU core speed poly")

    cpu_samples = numpy.linspace(
        start=_CPU_SAMPLES_START,
        stop=_CPU_SAMPLES_STOP,
        num=_CPU_SAMPLES_NUM)

    speeds = [(0.0, 0.0)] + [
        (cpus, get_cpu_core_speed(cpus))
        for cpus in cpu_samples
    ]

    _logger.debug("CPU speed dataset:\n%s", pprint.pformat(speeds))

    cpu_ratio = [item[0] for item in speeds]
    cpu_speed = [item[1] for item in speeds]
    coeffs = numpy.polyfit(cpu_ratio, cpu_speed, deg=1)
    poly = numpy.poly1d(coeffs)

    _logger.debug("CPU speed poly: %s", poly)

    _cache[_CACHE_POLY] = poly

    return poly


def get_docker_cpus(target_core_speed, core_poly=None):
    core_poly = core_poly if core_poly else get_cpu_core_speed_poly()
    max_core_speed = core_poly(1.0)

    if target_core_speed > max_core_speed:
        warn_msg = (
            "Target speed ({}) is higher than "
            "the host's max core speed ({})"
        ).format(target_core_speed, max_core_speed)

        _logger.warning(warn_msg)
        warnings.warn(warn_msg, Warning)

    _logger.debug("Solving %s for %s", core_poly, target_core_speed)

    coeffs = core_poly.coeffs.copy()
    coeffs[-1] -= target_core_speed
    roots = numpy.roots(coeffs)

    _logger.debug("Poly roots: %s", roots)

    cpus = float(numpy.real(roots[numpy.isreal(roots)][0]))
    cpus = max(cpus, 1e-2)

    _logger.debug(
        "Target core speed: %s ~ Docker cpus: %s",
        target_core_speed, cpus)

    return cpus
