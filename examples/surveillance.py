import json

from wotemu.enums import NetworkConditions
from wotemu.topology.models import (BuiltinApps, Network, Node, NodeApp,
                                    NodeResources, Topology)


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

    nodes_camera = [
        Node(
            name=f"camera_num_{idx}",
            app=NodeApp(path=BuiltinApps.CAMERA, http=True),
            networks=[network_field],
            resources=camera_resources)
        for idx in range(5)
    ]

    camera_hostnames = [
        f"{item.name}.{network_field.name}"
        for item in nodes_camera
    ]

    detector_resources = NodeResources(
        target_cpu_speed=600,
        mem_limit="1G")

    param_cameras = json.dumps([
        {"servient_host": cam_name}
        for cam_name in camera_hostnames
    ])

    app_detector = NodeApp(
        path=BuiltinApps.DETECTOR,
        params={"cameras": param_cameras})

    node_detector = Node(
        name="detector",
        app=app_detector,
        networks=[network_field, network_edge_link],
        resources=detector_resources)

    node_cloud_server = Node(
        name="cloud_server",
        app=NodeApp(path=BuiltinApps.CLOCK, http=True),
        networks=[network_edge_link, network_cloud_user])

    node_user = Node(
        name="user",
        app=NodeApp(path=BuiltinApps.CLOCK, http=True),
        networks=[network_cloud_user])

    topology = Topology(nodes=[
        *nodes_camera,
        node_detector,
        node_cloud_server,
        node_user
    ])

    return topology
