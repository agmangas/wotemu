import copy

from wotsim.enums import Labels

COMPOSE_VERSION = "3.7"
BASE_IMAGE = "wotsim"
TASK_NAME_HOSTNAME = "{{.Task.Name}}"
ENV_KEY_PATCH_PRIVILEGED = "PATCH_PRIVILEGED"
ENV_KEY_BROKER = "MQTT_BROKER_HOST"
ENV_VAL_FLAG = "1"
VOL_DOCKER_SOCK = "/var/run/docker.sock:/var/run/docker.sock"
NAME_DOCKER_PROXY = "docker_api_proxy"
NAME_REDIS = "redis"

SERVICE_BASE_DOCKER_PROXY = {
    "image": "tecnativa/docker-socket-proxy",
    "environment": {
        "CONTAINERS": ENV_VAL_FLAG,
        "NETWORKS": ENV_VAL_FLAG,
        "TASKS": ENV_VAL_FLAG,
        ENV_KEY_PATCH_PRIVILEGED: ENV_VAL_FLAG
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
    "hostname": TASK_NAME_HOSTNAME,
    "volumes": [VOL_DOCKER_SOCK],
    "labels": {Labels.WOTSIM_GATEWAY.value: ""},
    "environment": {ENV_KEY_PATCH_PRIVILEGED: ENV_VAL_FLAG}
}

SERVICE_BASE_BROKER = {
    "image": BASE_IMAGE,
    "privileged": True,
    "hostname": TASK_NAME_HOSTNAME,
    "environment": {ENV_KEY_PATCH_PRIVILEGED: ENV_VAL_FLAG}
}

SERVICE_BASE_NODE = {
    "privileged": True,
    "hostname": TASK_NAME_HOSTNAME,
    "environment": {ENV_KEY_PATCH_PRIVILEGED: ENV_VAL_FLAG}
}

NETWORK_BASE = {
    "driver": "overlay",
    "attachable": True,
    "labels": {Labels.WOTSIM_NETWORK.value: ""}
}


def _merge_topology_config(service, topology):
    envr = service.get("environment", {})

    envr.update({
        key.value: str(val)
        for key, val in topology.config.items()
        if val is not None
    })

    service["environment"] = envr


def get_docker_proxy_definition(topology):
    service = copy.deepcopy(SERVICE_BASE_DOCKER_PROXY)

    service.update({
        "networks": [net.name for net in topology.networks]
    })

    return {NAME_DOCKER_PROXY: service}


def get_redis_definition(topology):
    service = copy.deepcopy(SERVICE_BASE_REDIS)

    service.update({
        "networks": [net.name for net in topology.networks]
    })

    return {NAME_REDIS: service}


def get_network_gateway_definition(topology, network):
    service = copy.deepcopy(SERVICE_BASE_GATEWAY)

    service.update({
        "command": network.cmd_gateway,
        "networks": [network.name]
    })

    if network.args_compose_gw:
        service.update(network.args_compose_gw)

    _merge_topology_config(service, topology)

    return {network.name_gateway: service}


def get_network_definition(topology, network):
    definition = copy.deepcopy(NETWORK_BASE)
    definition.update({"name": network.name})
    return {network.name: definition}


def get_broker_definition(topology, broker):
    service = copy.deepcopy(SERVICE_BASE_BROKER)

    depends_on = [NAME_DOCKER_PROXY]
    depends_on += [net.name_gateway for net in broker.networks]

    service.update({
        "networks": [net.name for net in broker.networks],
        "depends_on": depends_on
    })

    if broker.args_compose:
        service.update(broker.args_compose)

    _merge_topology_config(service, topology)

    return {broker.name: service}


def get_node_resources_deploy_dict(node_resources):
    limits = {
        "cpus": node_resources.cpu_limit,
        "memory": node_resources.mem_limit
    }

    reservations = {}

    if node_resources.cpu_reservation:
        reservations.update({"cpus": node_resources.cpu_reservation})

    if node_resources.mem_reservation:
        reservations.update({"memory": node_resources.mem_reservation})

    ret = {"limits": limits}

    if len(reservations) > 0:
        ret.update({"reservations": reservations})

    return ret


def get_node_definition(topology, node):
    service = copy.deepcopy(SERVICE_BASE_NODE)

    networks = [net.name for net in node.networks]
    depends_on = [NAME_DOCKER_PROXY]
    depends_on += [net.name_gateway for net in node.networks]
    envr = service.get("environment", {})

    if node.broker:
        assert node.broker_network
        networks.append(node.broker_network.name)
        depends_on.append(node.broker_network.name_gateway)
        envr.update({ENV_KEY_BROKER: node.broker_host})

    service.update({
        "image": node.image,
        "command": node.cmd_app,
        "networks": list(set(networks)),
        "depends_on": list(set(depends_on)),
        "environment": envr
    })

    if node.resources:
        deploy = service.get("deploy", {})
        resources_dict = get_node_resources_deploy_dict(node.resources)
        deploy.update({"resources": resources_dict})
        service.update({"deploy": deploy})

    if node.args_compose:
        service.update(node.args_compose)

    _merge_topology_config(service, topology)

    return {node.name: service}


def get_topology_definition(topology):
    definition = {"version": COMPOSE_VERSION}

    services = {}
    services.update(get_docker_proxy_definition(topology))
    services.update(get_redis_definition(topology))

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
