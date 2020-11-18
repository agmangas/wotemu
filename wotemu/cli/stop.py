import logging
import pprint
import re

import docker
import sh
import yaml
from wotemu.enums import Labels

_STACK_NAMESPACE = "com.docker.stack.namespace"

_logger = logging.getLogger(__name__)


def _assert_stack_exists(stack):
    docker_api_client = docker.APIClient()

    stack_services = [
        item for item in docker_api_client.services()
        if item.get("Spec", {}).get("Labels", {}).get(_STACK_NAMESPACE) == stack
    ]

    if len(stack_services) == 0:
        raise Exception(f"No services found for stack: {stack}")


def stop_stack(conf, compose_file, stack):
    _assert_stack_exists(stack=stack)

    _logger.info("Opening Compose file: %s", compose_file)

    with open(compose_file, "r") as fh:
        content = yaml.load(fh.read(), Loader=yaml.FullLoader)

    _logger.debug("Compose file:\n%s", pprint.pformat(content))

    services = content.get("services", {})

    services = {
        key: val
        for key, val in services.items()
        if val.get("labels", {}).get(Labels.WOTEMU_REDIS.value, None) is not None
    }

    content["services"] = services

    _logger.debug("Compose file (target):\n%s", pprint.pformat(content))
    _logger.info("Updating stack '%s'", stack)

    sh_docker = sh.Command("docker")

    proc = sh_docker(
        ["stack", "deploy", "-c", "-", stack],
        _err_to_out=True,
        _in=yaml.dump(content))

    _logger.info("%s\n%s", proc.ran, str(proc).strip())
