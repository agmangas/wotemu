import asyncio
import logging
import pprint
import re
import time

import docker
import tornado.httpclient

from wotsim.enums import Labels

_CGROUP_PATH = "/proc/self/cgroup"
_STACK_NAMESPACE = "com.docker.stack.namespace"
_CID_HOST_LEN = 12

_logger = logging.getLogger(__name__)


class NodeHTTPTimeout(Exception):
    pass


async def _ping_http(url):
    http_client = tornado.httpclient.AsyncHTTPClient()

    try:
        await http_client.fetch(url)
        _logger.debug("HTTP ping OK: %s", url)
        return True
    except Exception as ex:
        _logger.debug("HTTP ping Error (%s): %s", url, ex)
        return False
    finally:
        http_client.close()


async def _ping_http_timeout(url, wait, timeout):
    _logger.debug("HTTP ping (%s secs timeout): %s", timeout, url)

    ini = time.time()

    def _raise_timeout():
        if timeout is None:
            return

        diff = time.time() - ini

        if diff >= timeout:
            raise NodeHTTPTimeout(
                "HTTP timeout ({} s): {}".format(timeout, url))

    while True:
        _raise_timeout()

        if (await _ping_http(url)):
            break

        _raise_timeout()
        await asyncio.sleep(wait)


async def wait_node(conf, node_name, wait=2, timeout=300, passes=3):
    docker_api_client = docker.APIClient(base_url=conf.docker_proxy_url)

    _logger.debug("Waiting for node: %s", node_name)
    service_parts = node_name.split(".")

    try:
        network_candidate = service_parts[-1]
        _logger.debug("Checking network existence: %s", network_candidate)
        docker_api_client.inspect_network(network_candidate)
        service_name = ".".join(service_parts[:-1])
    except docker.errors.NotFound:
        _logger.debug("Network does not exist: %s", network_candidate)
        service_name = node_name

    namespace = get_current_stack_namespace(conf.docker_proxy_url)

    if not service_name.startswith(namespace):
        _logger.debug("Adding namespace prefix to service: %s", namespace)
        service_name = "{}_{}".format(namespace, service_name)

    _logger.debug("Service name: %s", service_name)

    try:
        docker_api_client.inspect_service(service_name)
    except docker.errors.NotFound as ex:
        _logger.warning("Service (%s) not found: %s", service_name, ex)
        return

    service_tasks = docker_api_client.tasks(filters={
        "service": service_name
    })

    _logger.debug("Found %s tasks for %s", len(service_tasks), service_name)

    cont_hosts = [
        task["Status"]["ContainerStatus"]["ContainerID"][:_CID_HOST_LEN]
        for task in service_tasks
    ]

    _logger.debug("Service %s container hosts: %s", service_name, cont_hosts)

    urls = [
        "http://{}:{}".format(host, conf.port_catalogue)
        for host in cont_hosts
    ]

    _logger.debug("Catalogue URLs: %s", urls)

    await asyncio.gather(*[
        _ping_http_timeout(url=url, wait=wait, timeout=timeout)
        for url in urls
    ])


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


def get_current_stack_namespace(docker_url):
    curr_task = get_current_task(docker_url=docker_url)
    return curr_task.get("Spec", {}).get("ContainerSpec", {}).get("Labels", {}).get(_STACK_NAMESPACE, None)


def get_current_service(docker_url):
    curr_task = get_current_task(docker_url=docker_url)
    curr_service_id = curr_task["ServiceID"]
    docker_api_client = docker.APIClient(base_url=conf.docker_proxy_url)

    return docker_api_client.inspect_service(curr_service_id)


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
