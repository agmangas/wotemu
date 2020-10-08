import copy

from deepmerge import always_merger

from wotemu.config import DEFAULT_DOCKER_SOCKET, ConfigVars
from wotemu.enums import Labels

COMPOSE_VERSION = "3.7"
BASE_IMAGE = "wotemu"
TEMPLATE_TASK_NAME = "{{.Task.Name}}"
TEMPLATE_NODE_HOST = "{{.Node.Hostname}}"
TEMPLATE_NODE_ID = "{{.Node.ID}}"
ENV_KEY_CPU_SPEED = "TARGET_CPU_SPEED"
ENV_KEY_PRIVILEGED = "PATCH_PRIVILEGED"
ENV_KEY_NODE_HOST = "NODE_HOSTNAME"
ENV_KEY_NODE_ID = "NODE_ID"
ENV_KEY_CPU_SPEED = "TARGET_CPU_SPEED"
ENV_VAL_FLAG = "1"
VOL_DOCKER_SOCK = "{}:{}".format(DEFAULT_DOCKER_SOCKET, DEFAULT_DOCKER_SOCKET)

SERVICE_BASE_DOCKER_PROXY = {
    "image": "tecnativa/docker-socket-proxy",
    "environment": {
        "CONTAINERS": ENV_VAL_FLAG,
        "NETWORKS": ENV_VAL_FLAG,
        "TASKS": ENV_VAL_FLAG,
        "SERVICES": ENV_VAL_FLAG,
        "NODES": ENV_VAL_FLAG,
        ENV_KEY_PRIVILEGED: ENV_VAL_FLAG
    },
    "deploy": {
        "placement": {
            "constraints": ["node.role == manager"]
        }
    },
    "privileged": True,
    "volumes": [VOL_DOCKER_SOCK]
}

SERVICE_BASE_REDIS = {
    "image": "redis:5"
}

SERVICE_BASE_GATEWAY = {
    "image": BASE_IMAGE,
    "privileged": True,
    "hostname": TEMPLATE_TASK_NAME,
    "volumes": [VOL_DOCKER_SOCK],
    "labels": {Labels.WOTEMU_GATEWAY.value: ""},
    "environment": {
        ENV_KEY_PRIVILEGED: ENV_VAL_FLAG,
        ENV_KEY_NODE_HOST: TEMPLATE_NODE_HOST,
        ENV_KEY_NODE_ID: TEMPLATE_NODE_ID
    }
}

SERVICE_BASE_BROKER = {
    "image": BASE_IMAGE,
    "privileged": True,
    "hostname": TEMPLATE_TASK_NAME,
    "volumes": [VOL_DOCKER_SOCK],
    "labels": {Labels.WOTEMU_BROKER.value: ""},
    "environment": {
        ENV_KEY_PRIVILEGED: ENV_VAL_FLAG,
        ENV_KEY_NODE_HOST: TEMPLATE_NODE_HOST,
        ENV_KEY_NODE_ID: TEMPLATE_NODE_ID
    }
}

SERVICE_BASE_NODE = {
    "privileged": True,
    "hostname": TEMPLATE_TASK_NAME,
    "volumes": [VOL_DOCKER_SOCK],
    "labels": {Labels.WOTEMU_NODE.value: ""},
    "environment": {
        ENV_KEY_PRIVILEGED: ENV_VAL_FLAG,
        ENV_KEY_NODE_HOST: TEMPLATE_NODE_HOST,
        ENV_KEY_NODE_ID: TEMPLATE_NODE_ID
    }
}

NETWORK_BASE = {
    "driver": "overlay",
    "attachable": True,
    "labels": {Labels.WOTEMU_NETWORK.value: ""}
}


def _merge_topology_config(service, topology):
    envr = service.get("environment", {})

    envr.update({
        key: str(val)
        for key, val in topology.config.items()
        if val is not None
    })

    service["environment"] = envr


def get_docker_proxy_definition(topology):
    service = copy.deepcopy(SERVICE_BASE_DOCKER_PROXY)

    service.update({
        "networks": [net.name for net in topology.networks]
    })

    return {topology.docker_proxy.host: service}


def get_redis_definition(topology, topology_redis):
    service = copy.deepcopy(SERVICE_BASE_REDIS)

    service.update({
        "networks": [net.name for net in topology.networks],
        "ports": [f"{topology_redis.public_port}:6379"]
    })

    return {topology.redis.host: service}


def get_network_gateway_definition(topology, network):
    service = copy.deepcopy(SERVICE_BASE_GATEWAY)

    depends_on = []

    if topology.docker_proxy.enabled:
        depends_on.append(topology.docker_proxy.host)

    if topology.redis.enabled:
        depends_on.append(topology.redis.host)

    service.update({
        "command": network.cmd_gateway,
        "networks": [network.name],
        "depends_on": depends_on
    })

    if network.args_compose_gw:
        always_merger.merge(service, network.args_compose_gw)

    _merge_topology_config(service, topology)

    return {network.name_gateway: service}


def get_network_definition(topology, network):
    definition = copy.deepcopy(NETWORK_BASE)
    definition.update({"name": network.name})
    return {network.name: definition}


def get_broker_definition(topology, broker):
    service = copy.deepcopy(SERVICE_BASE_BROKER)

    depends_on = [
        *[net.name_gateway for net in broker.networks]
    ]

    if topology.docker_proxy.enabled:
        depends_on.append(topology.docker_proxy.host)

    if topology.redis.enabled:
        depends_on.append(topology.redis.host)

    service.update({
        "command": broker.cmd,
        "networks": [net.name for net in broker.networks],
        "depends_on": depends_on
    })

    if broker.args_compose:
        always_merger.merge(service, broker.args_compose)

    _merge_topology_config(service, topology)

    return {broker.name: service}


def get_node_resources_definition(node_resources):
    limits = {}

    if node_resources.cpu_limit:
        limits.update({"cpus": node_resources.cpu_limit})

    if node_resources.mem_limit:
        limits.update({"memory": node_resources.mem_limit})

    reserv = {}

    if node_resources.cpu_reservation:
        reserv.update({"cpus": node_resources.cpu_reservation})

    if node_resources.mem_reservation:
        reserv.update({"memory": node_resources.mem_reservation})

    ret = {}

    if len(limits) > 0:
        ret.update({"limits": limits})

    if len(reserv) > 0:
        ret.update({"reservations": reserv})

    return ret if len(ret) > 0 else None


def get_node_definition(topology, node):
    service = copy.deepcopy(SERVICE_BASE_NODE)

    networks = [net.name for net in node.networks]

    depends_on = [
        *[net.name_gateway for net in node.networks]
    ]

    if topology.docker_proxy.enabled:
        depends_on.append(topology.docker_proxy.host)

    if topology.redis.enabled:
        depends_on.append(topology.redis.host)

    envr = service.get("environment", {})

    if node.broker:
        assert node.broker_network
        networks.append(node.broker_network.name)
        depends_on.append(node.broker_network.name_gateway)
        envr.update({ConfigVars.MQTT_BROKER_HOST.value: node.broker_host})

    service.update({
        "image": node.image,
        "command": node.cmd_app,
        "networks": list(set(networks)),
        "depends_on": list(set(depends_on)),
        "environment": envr
    })

    deploy = service.get("deploy", {})

    if node.resources:
        resources_dict = get_node_resources_definition(node.resources)

        if resources_dict:
            deploy.update({"resources": resources_dict})

        if node.resources.target_cpu_speed:
            env_speed = {ENV_KEY_CPU_SPEED: node.resources.target_cpu_speed}
            always_merger.merge(service, {"environment": env_speed})

    if node.scale:
        deploy.update({"replicas": node.scale})

    if len(deploy) > 0:
        service.update({"deploy": deploy})

    if node.args_compose:
        always_merger.merge(service, node.args_compose)

    _merge_topology_config(service, topology)

    return {node.name: service}


def get_topology_definition(topology):
    definition = {"version": COMPOSE_VERSION}

    services = {}

    if topology.docker_proxy.enabled:
        services.update(topology.docker_proxy_compose_dict)

    if topology.redis.enabled:
        services.update(topology.redis_compose_dict)

    for net in topology.networks:
        services.update(net.to_gateway_compose_dict(topology))

    for node in topology.nodes:
        services.update(node.to_compose_dict(topology))

    for broker in topology.brokers:
        services.update(broker.to_compose_dict(topology))

    networks = {}

    for net in topology.networks:
        networks.update(net.to_compose_dict(topology))

    definition.update({
        "services": services,
        "networks": networks
    })

    return definition
