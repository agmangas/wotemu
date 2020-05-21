import copy

from wotsim.enums import Labels

ENTRY_GATEWAY = "gateway"
ENTRY_APP = "app"
BASE_IMAGE = "wotsim"
BASE_HOSTNAME = "{{.Task.Name}}"
ENV_PATCH_PRIVILEGED = "PATCH_PRIVILEGED=1"
ENV_KEY_BROKER = "MQTT_BROKER_HOST"
DOCKER_SOCK_VOLUME = "/var/run/docker.sock:/var/run/docker.sock"
NAME_DOCKER_PROXY = "docker_api_proxy"
NAME_REDIS = "redis"

SERVICE_BASE_DOCKER_PROXY = {
    "image": "tecnativa/docker-socket-proxy",
    "environment": [
        "CONTAINERS=1",
        "NETWORKS=1",
        "TASKS=1",
        "PATCH_PRIVILEGED=1"
    ],
    "deploy": {
        "placement": {
            "constraints": ["node.role == manager"]
        }
    },
    "privileged": True,
    "volumes": [DOCKER_SOCK_VOLUME]
}

SERVICE_BASE_REDIS = {
    "image": "redis:5"
}

SERVICE_BASE_GATEWAY = {
    "image": BASE_IMAGE,
    "privileged": True,
    "hostname": BASE_HOSTNAME,
    "volumes": [DOCKER_SOCK_VOLUME],
    "labels": [Labels.WOTSIM_GATEWAY.value],
    "environment": [ENV_PATCH_PRIVILEGED]
}

SERVICE_BASE_BROKER = {
    "image": BASE_IMAGE,
    "privileged": True,
    "hostname": BASE_HOSTNAME,
    "environment": [ENV_PATCH_PRIVILEGED]
}

SERVICE_BASE_NODE = {
    "privileged": True,
    "hostname": BASE_HOSTNAME,
    "environment": [ENV_PATCH_PRIVILEGED]
}


def get_docker_proxy_definition(topology):
    service = copy.deepcopy(SERVICE_BASE_DOCKER_PROXY)

    service.update({
        "networks": [net.name for net in topology.networks]
    })

    return {topology.name_docker_proxy: service}


def get_redis_definition(topology):
    service = copy.deepcopy(SERVICE_BASE_REDIS)

    service.update({
        "networks": [net.name for net in topology.networks]
    })

    return {topology.name_redis: service}


def get_network_gateway_definition(topology, network):
    service = copy.deepcopy(SERVICE_BASE_GATEWAY)

    service.update({
        "command": [ENTRY_GATEWAY] + list(network.netem_args),
        "networks": [network.name]
    })

    if network.args_compose_gw:
        service.update(network.args_compose_gw)

    return {network.name_gateway: service}


def get_broker_definition(topology, broker):
    service = copy.deepcopy(SERVICE_BASE_BROKER)

    service.update({
        "networks": [broker.network.name],
        "depends_on": [
            topology.name_docker_proxy,
            broker.network.name_gateway
        ]
    })

    if broker.args_compose:
        service.update(broker.args_compose)

    return {broker.name: service}


def get_node_definition(topology, node):
    service = copy.deepcopy(SERVICE_BASE_NODE)

    networks = [net.name for net in node.networks]
    depends_on = [topology.name_docker_proxy]
    depends_on += [net.name_gateway for net in node.networks]
    envr = service.get("environment", [])

    if node.broker:
        networks.append(node.broker.network.name)
        depends_on.append(node.broker.network.name_gateway)
        envr.append("{}={}".format(ENV_KEY_BROKER, node.broker_host))

    service.update({
        "image": node.image,
        "command": [ENTRY_APP] + list(node.app.app_args),
        "networks": list(set(networks)),
        "depends_on": list(set(depends_on)),
        "environment": envr
    })

    if node.args_compose:
        service.update(node.args_compose)

    return {node.name: service}
