import asyncio
import logging
import pprint
import time

import docker
import tornado.httpclient

import wotsim.config
from wotsim.cli.utils import (get_current_task, get_task_labels,
                              get_task_networks)
from wotsim.enums import Labels

_logger = logging.getLogger(__name__)


async def _ping_http(url):
    http_client = tornado.httpclient.AsyncHTTPClient()

    try:
        await http_client.fetch(url)
        _logger.debug("Ping OK (%s)", url)
        return True
    except Exception as ex:
        _logger.debug("Ping Error (%s): %s", url, ex)
        return False
    finally:
        http_client.close()


async def _ping_http_timeout(url, wait, timeout):
    ini = time.time()

    def _raise_timeout():
        diff = time.time() - ini

        if diff >= timeout:
            raise Exception("Timeout ({} s) for URL: {}".format(timeout, url))

    while True:
        _raise_timeout()

        if (await _ping_http(url)):
            break

        _raise_timeout()
        await asyncio.sleep(wait)


async def _wait_task_node(conf, task_name, wait, timeout):
    catalogue_url = "http://{}:{}".format(task_name, conf.port_catalogue)

    await _ping_http_timeout(
        url=catalogue_url,
        wait=wait,
        timeout=timeout)


async def _wait_task(conf, docker_url, task_name, wait, timeout):
    task_labels = get_task_labels(
        docker_url=docker_url,
        task_name=task_name)

    if Labels.WOTSIM_NODE.value in task_labels:
        _logger.debug("Waiting for node: %s", task_name)
        await _wait_task_node(conf, task_name, wait, timeout)


def _get_network_task_names(docker_url, network_id):
    docker_api_client = docker.APIClient(base_url=docker_url)
    network_info = docker_api_client.inspect_network(network_id, verbose=True)

    return [
        task["Name"]
        for service in network_info["Services"].values()
        for task in service["Tasks"]
    ]


async def wait_nodes(conf, wait=2, timeout=300):
    docker_url = conf.docker_proxy_url
    task = get_current_task(docker_url=docker_url)
    network_ids = get_task_networks(docker_url=docker_url, task=task)

    network_tasks = {
        net_id: _get_network_task_names(docker_url, net_id)
        for net_id in network_ids
    }

    await asyncio.gather(*(
        _wait_task(conf, docker_url, task_name, wait, timeout)
        for task_names in network_tasks.values()
        for task_name in task_names
    ))
