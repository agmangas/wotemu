import logging
import re

import docker

_logger = logging.getLogger(__name__)


def ping_docker(docker_url):
    try:
        docker_client = docker.DockerClient(base_url=docker_url)
        docker_client.ping()
    except Exception as ex:
        raise Exception("Could not ping Docker daemon: {}".format(ex))


def current_container_id():
    cgroup_path = "/proc/self/cgroup"

    with open(cgroup_path, "r") as fh:
        cgroup = fh.read()

    cid_regex = r"\d+:.+:\/docker\/([a-zA-Z0-9]+)"

    _logger.debug("%s:\n%s", cgroup_path, cgroup)
    _logger.debug("Applying '%s' to cgroup content", cid_regex)

    result = re.search(cid_regex, cgroup)

    if not result or len(result.groups()) <= 0:
        raise Exception("Could not retrieve container ID")

    cid = result.groups()[0]

    _logger.debug("Current container ID: %s", cid)

    return cid


def strip_ansi_codes(val):
    """Attribution to: https://stackoverflow.com/a/15780675"""

    return re.sub(r'\x1b\[([0-9,A-Z]{1,2}(;[0-9]{1,2})?(;[0-9]{3})?)?[m|K]?', "", val)
