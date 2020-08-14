import asyncio
import importlib
import logging
import os
import pprint
import re
import sys
import time

import docker
import netaddr
import netifaces
import tornado.httpclient

from wotemu.enums import Labels

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


async def wait_node(conf, name, wait=2, timeout=300, find_replicas=True):
    cont_hosts = [name]

    if find_replicas:
        _logger.debug((
            "Attempting to translate service name '%s' "
            "to the container hostnames of all the "
            "replicas for that service"
        ), name)

        try:
            cont_hosts = get_service_container_hostnames(
                docker_url=conf.docker_proxy_url,
                name=name)
        except docker.errors.NotFound as ex:
            _logger.warning("Error finding container hostnames: %s", ex)

    urls = [
        "http://{}:{}".format(host, conf.port_catalogue)
        for host in cont_hosts
    ]

    _logger.debug("Catalogue URLs: %s", urls)

    ping_awaitables = [
        _ping_http_timeout(url=url, wait=wait, timeout=timeout)
        for url in urls
    ]

    await asyncio.gather(*ping_awaitables)


def get_service_container_hostnames(docker_url, name):
    docker_api_client = docker.APIClient(base_url=docker_url)

    _logger.debug("Finding container hostnames for: %s", name)
    service_parts = name.split(".")

    try:
        network_candidate = service_parts[-1]
        _logger.debug("Checking network existence: %s", network_candidate)
        docker_api_client.inspect_network(network_candidate)
        inspect_name = ".".join(service_parts[:-1])
    except docker.errors.NotFound:
        _logger.debug("Network does not exist: %s", network_candidate)
        inspect_name = name

    namespace = get_current_stack_namespace(docker_url)

    if not inspect_name.startswith(namespace):
        _logger.debug("Adding namespace prefix: %s", namespace)
        inspect_name = "{}_{}".format(namespace, inspect_name)

    _logger.debug("Service name: %s", inspect_name)

    service_tasks = docker_api_client.tasks(
        filters={"service": inspect_name})

    _logger.debug("Found %s tasks for %s", len(service_tasks), inspect_name)

    cont_hosts = [
        task["Status"]["ContainerStatus"]["ContainerID"][:_CID_HOST_LEN]
        for task in service_tasks
    ]

    _logger.debug("Service %s container hosts: %s", inspect_name, cont_hosts)

    return cont_hosts


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
        if net_info.get("Labels", {}).get(Labels.WOTEMU_NETWORK.value, None) is not None
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
        if labels.get(Labels.WOTEMU_GATEWAY.value, None) is not None)


def get_output_iface_for_remote_task(remote_task):
    rtask_name = remote_task["Name"]
    rtask_addr = netaddr.IPAddress(remote_task["EndpointIP"])

    iface_addrs = {
        name: netifaces.ifaddresses(name).get(netifaces.AF_INET)
        for name in netifaces.interfaces()
        if netifaces.ifaddresses(name).get(netifaces.AF_INET)
    }

    _logger.debug(
        "Current container interfaces:\n%s",
        pprint.pformat(iface_addrs))

    ret = next(
        (iface_name, addr)
        for iface_name, iface_addrs in iface_addrs.items()
        for addr in iface_addrs
        if rtask_addr in netaddr.IPNetwork("{}/{}".format(addr["addr"], addr["netmask"])))

    _logger.debug(
        "Output interface for %s:\n%s",
        rtask_name, pprint.pformat(ret))

    return ret


def strip_ansi_codes(val):
    """Attribution to: https://stackoverflow.com/a/15780675"""

    return re.sub(r'\x1b\[([0-9,A-Z]{1,2}(;[0-9]{1,2})?(;[0-9]{3})?)?[m|K]?', "", val)


def import_func(module_path, func_name):
    _logger.debug("Attempting to import module: %s", module_path)

    path_root, path_base = os.path.split(module_path)

    if path_root not in sys.path:
        sys.path.insert(0, path_root)

    mod_name, _ext = os.path.splitext(path_base)
    mod_import = importlib.import_module(mod_name)
    mod_dir = dir(mod_import)

    _logger.info("Imported: %s", mod_import)
    _logger.debug("dir(%s): %s", mod_import, mod_dir)

    if func_name not in mod_dir:
        raise Exception("Module {} does not contain function '{}'".format(
            mod_import, func_name))

    return getattr(mod_import, func_name)
