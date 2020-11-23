import asyncio
import json
import logging
import pprint
import time

import aioredis
import docker
import sh
import yaml
from wotemu.enums import Labels, RedisPrefixes

_REDIS_PORT = 6379
_STACK_NAMESPACE = "com.docker.stack.namespace"

_logger = logging.getLogger(__name__)


def _find_stack_services(stack):
    docker_api_client = docker.APIClient()

    return [
        item for item in docker_api_client.services()
        if item.get("Spec", {}).get("Labels", {}).get(_STACK_NAMESPACE) == stack
    ]


def _assert_stack_exists(stack):
    services = _find_stack_services(stack=stack)

    if len(services) == 0:
        raise Exception(f"No services found for stack: {stack}")


def _get_task_logs(task, tail=30):
    sh_docker = sh.Command("docker")
    cmd_parts = ["service", "logs", "--tail", tail, task["ID"]]

    try:
        _logger.debug("Running: %s", cmd_parts)
        proc = sh_docker(cmd_parts, _err_to_out=True)
    except sh.ErrorReturnCode as ex:
        _logger.warning("Error running %s: %s", cmd_parts, ex)
        return None

    return proc.stdout.decode("utf8")


def _get_stack_snapshot(stack, tail):
    docker_api_client = docker.APIClient()
    services = _find_stack_services(stack=stack)

    _logger.info(
        "Inspecting tasks for %s services found on stack: %s",
        len(services), stack)

    return {
        task["ID"]: {
            "task": task,
            "time": time.time(),
            "logs": _get_task_logs(task, tail=tail)
        }
        for service in services
        for task in docker_api_client.tasks(filters={"service": service["ID"]})
    }


def _is_redis(service):
    return service.get("labels", {}).get(Labels.WOTEMU_REDIS.value, None) is not None


async def _write_snapshot(redis_url, data):
    key = "{}:{}".format(
        RedisPrefixes.NAMESPACE.value,
        RedisPrefixes.SNAPSHOT.value)

    try:
        redis = await aioredis.create_redis_pool(redis_url)
        score = time.time()
        member = json.dumps(data)
        _logger.info("Writing snapshot (%s bytes)", len(member))
        await redis.zadd(key=key, score=score, member=member)
    except:
        _logger.warning("Error writing snapshot", exc_info=True)
    finally:
        try:
            redis.close()
            await redis.wait_closed()
        except:
            _logger.warning("Error closing Redis", exc_info=True)


def _find_stack_redis_port(stack):
    _logger.info("Finding publicly exposed Redis port for stack: %s", stack)

    services = _find_stack_services(stack=stack)

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


def stop_stack(conf, compose_file, stack, redis_url, tail):
    _assert_stack_exists(stack=stack)

    _logger.info("Opening Compose file: %s", compose_file)

    with open(compose_file, "r") as fh:
        content = yaml.load(fh.read(), Loader=yaml.FullLoader)

    _logger.debug("Compose file:\n%s", pprint.pformat(content))

    services = content.get("services", {})

    for service in services.values():
        if not _is_redis(service):
            service.update({"deploy": {"replicas": 0}})

    content["services"] = services

    _logger.debug("Compose file (target):\n%s", pprint.pformat(content))

    stack_snapshot = _get_stack_snapshot(stack=stack, tail=tail)

    _logger.info("Updating stack: %s", stack)

    sh_docker = sh.Command("docker")

    proc = sh_docker(
        ["stack", "deploy", "-c", "-", stack],
        _err_to_out=True,
        _in=yaml.dump(content))

    _logger.info("%s\n%s", proc.ran, str(proc).strip())

    if not redis_url:
        redis_port = _find_stack_redis_port(stack=stack)
        redis_url = f"redis://127.0.0.1:{redis_port}"

    _logger.info("Using Redis URL: %s", redis_url)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_write_snapshot(redis_url, stack_snapshot))

    _logger.info("Stack stopped successfully: %s", stack)
