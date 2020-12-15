import logging
import pprint

import docker
from wotemu.enums import Labels

_REDIS_PORT = 6379
_STACK_NAMESPACE = "com.docker.stack.namespace"

_logger = logging.getLogger(__name__)


def find_stack_services(stack, api_client=None):
    api_client = api_client or docker.APIClient()

    return [
        item for item in api_client.services()
        if item.get("Spec", {}).get("Labels", {}).get(_STACK_NAMESPACE) == stack
    ]


def find_stack_redis_port(stack, api_client=None):
    _logger.info("Finding publicly exposed Redis port for stack: %s", stack)

    services = find_stack_services(stack=stack, api_client=api_client)

    redis_service = next(
        item
        for item in services
        if item.get("Spec", {}).
        get("TaskTemplate", {}).
        get("ContainerSpec", {}).
        get("Labels", {}).
        get(Labels.WOTEMU_REDIS.value, None) is not None)

    _logger.debug("Found Redis service:\n%s", pprint.pformat(redis_service))

    return next(
        item["PublishedPort"]
        for item in redis_service["Endpoint"]["Ports"]
        if item["TargetPort"] == _REDIS_PORT and item["Protocol"] == "tcp")
