import logging
import pprint
import re

import docker

from wotsim.enums import Labels

_CGROUP_PATH = "/proc/self/cgroup"

_logger = logging.getLogger(__name__)


def ping_docker(docker_url):
    try:
        docker_client = docker.DockerClient(base_url=docker_url)
        docker_client.ping()
    except Exception as ex:
        raise Exception("Could not ping Docker daemon: {}".format(ex))


def get_current_container_id():
    try:
        with open(_CGROUP_PATH, "r") as fh:
            cgroup = fh.read()
    except FileNotFoundError as ex:
        raise Exception((
            "The current environment does not "
            "seem to be a Docker container ({})"
        ).format(ex))

    cid_regex = r"\d+:.+:\/docker\/([a-zA-Z0-9]+)"

    _logger.debug("%s:\n%s", _CGROUP_PATH, cgroup)
    _logger.debug("Applying '%s' to cgroup content", cid_regex)

    result = re.search(cid_regex, cgroup)

    if not result or len(result.groups()) <= 0:
        raise Exception("Could not retrieve container ID")

    cid = result.groups()[0]

    _logger.debug("Current container ID: %s", cid)

    return cid


def get_task_container_id(task):
    return task.get("Status", {}).get("ContainerStatus", {}).get("ContainerID", None)


def get_current_task(docker_url):
    docker_api_client = docker.APIClient(base_url=docker_url)
    cid = get_current_container_id()

    task = next((
        task for task in docker_api_client.tasks()
        if get_task_container_id(task) == cid), None)

    if task is None:
        raise Exception("Could not find task for container: {}".format(cid))

    _logger.debug("Current task:\n%s", pprint.pformat(task))

    return task


def get_task_networks(docker_url, task):
    docker_api_client = docker.APIClient(base_url=docker_url)

    network_ids = [
        net["Network"]["ID"]
        for net in task["NetworksAttachments"]
    ]

    networks = {
        net_id: docker_api_client.inspect_network(net_id)
        for net_id in network_ids
    }

    networks = {
        net_id: net_info for net_id, net_info in networks.items()
        if net_info.get("Labels", {}).get(Labels.WOTSIM_NETWORK.value, None) is not None
    }

    _logger.debug("Simulator networks:\n%s", pprint.pformat(networks))

    return list(networks.keys())


def get_task_labels(docker_url, task_name):
    docker_api_client = docker.APIClient(base_url=docker_url)
    task_info = docker_api_client.inspect_task(task_name)

    return task_info["Spec"]["ContainerSpec"]["Labels"]


def get_network_gateway_task(docker_url, network_id):
    docker_api_client = docker.APIClient(base_url=docker_url)

    network_info = docker_api_client.inspect_network(network_id, verbose=True)

    service_infos = {
        net_name: info
        for net_name, info in network_info["Services"].items()
        if len(net_name) > 0
    }

    _logger.debug(
        "Network %s services:\n%s", network_id,
        pprint.pformat(list(service_infos.keys())))

    task_infos = {
        task_info["Name"]: task_info
        for net_name, serv_info in service_infos.items()
        for task_info in serv_info["Tasks"]
    }

    _logger.debug(
        "Network %s tasks:\n%s", network_id,
        pprint.pformat(list(task_infos.keys())))

    task_labels = {
        task_name: get_task_labels(docker_url, task_name)
        for task_name in task_infos.keys()
    }

    return next(
        task_infos[task_name]
        for task_name, labels in task_labels.items()
        if labels.get(Labels.WOTSIM_GATEWAY.value, None) is not None)


def strip_ansi_codes(val):
    """Attribution to: https://stackoverflow.com/a/15780675"""

    return re.sub(r'\x1b\[([0-9,A-Z]{1,2}(;[0-9]{1,2})?(;[0-9]{3})?)?[m|K]?', "", val)
