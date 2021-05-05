from wotemu.config import ConfigVars
from wotemu.enums import NetworkConditions
from wotemu.topology.models import (BuiltinApps, Network, Node, NodeApp,
                                    NodeResources, Topology)

_PORT_STREAM = 9898

_ARGS_COMPOSE_PORT_STREAM = {
    "environment": {
        ConfigVars.OTHER_PORTS_TCP.value: f"{_PORT_STREAM}",
        ConfigVars.OTHER_PORTS_UDP.value: f"{_PORT_STREAM}"
    }
}


def topology():
    network_field = Network(
        name="field",
        conditions=NetworkConditions.WIFI)

    network_edge_link = Network(
        name="edge_link",
        conditions=NetworkConditions.REGULAR_3G)

    network_cloud_user = Network(
        name="cloud_user",
        conditions=NetworkConditions.CABLE)

    camera_resources = NodeResources(
        target_cpu_speed=200,
        mem_limit="256M")

    node_camera = Node(
        name="camera",
        app=NodeApp(path=BuiltinApps.CAMERA, http=True),
        networks=[network_field],
        resources=camera_resources,
        args_compose=_ARGS_COMPOSE_PORT_STREAM)

    detector_resources = NodeResources(
        target_cpu_speed=600,
        mem_limit="1G")

    node_detector = Node(
        name="detector",
        app=NodeApp(path=BuiltinApps.CLOCK, http=True),
        networks=[network_field, network_edge_link],
        resources=detector_resources,
        args_compose=_ARGS_COMPOSE_PORT_STREAM)

    node_cloud_server = Node(
        name="cloud_server",
        app=NodeApp(path=BuiltinApps.CLOCK, http=True),
        networks=[network_edge_link, network_cloud_user])

    node_user = Node(
        name="user",
        app=NodeApp(path=BuiltinApps.CLOCK, http=True),
        networks=[network_cloud_user])

    topology = Topology(nodes=[
        node_camera,
        node_detector,
        node_cloud_server,
        node_user
    ])

    return topology
