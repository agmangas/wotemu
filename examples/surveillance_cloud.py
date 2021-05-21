import json

from docker.types import RestartPolicy
from wotemu.enums import NetworkConditions
from wotemu.topology.models import (Broker, BuiltinApps, Network, Node,
                                    NodeApp, NodeResources, Service, Topology)

_ID_1 = "loc1"
_ID_2 = "loc2"

_THING_ID_DETECTOR = "urn:org:fundacionctic:thing:wotemu:detector"
_THING_ID_HISTORIAN = "urn:org:fundacionctic:thing:historian"


def topology():
    network_edge_1 = Network(
        name=f"edge_2g_{_ID_1}",
        conditions=NetworkConditions.GPRS)

    network_edge_2 = Network(
        name=f"edge_3g_{_ID_2}",
        conditions=NetworkConditions.REGULAR_3G)

    network_cloud = Network(
        name="cloud",
        conditions=NetworkConditions.CABLE)

    network_cloud_user = Network(
        name="cloud_user",
        conditions=NetworkConditions.CABLE)

    broker = Broker(
        name=f"broker",
        networks=[network_edge_1, network_edge_2])

    camera_resources = NodeResources(
        target_cpu_speed=200,
        mem_limit="256M")

    nodes_camera_1 = [
        Node(
            name=f"camera_{_ID_1}_{idx}",
            app=NodeApp(path=BuiltinApps.CAMERA, mqtt=True),
            networks=[network_edge_1],
            resources=camera_resources,
            broker=broker,
            broker_network=network_edge_1)
        for idx in range(2)
    ]

    nodes_camera_2 = [
        Node(
            name=f"camera_{_ID_2}_{idx}",
            app=NodeApp(path=BuiltinApps.CAMERA, mqtt=True),
            networks=[network_edge_2],
            resources=camera_resources,
            broker=broker,
            broker_network=network_edge_2)
        for idx in range(8)
    ]

    camera_hostnames_1 = [
        f"{item.name}.{network_edge_1.name}"
        for item in nodes_camera_1
    ]

    camera_hostnames_2 = [
        f"{item.name}.{network_edge_2.name}"
        for item in nodes_camera_2
    ]

    param_cameras = json.dumps([
        {"servient_host": cam_name}
        for cam_name in camera_hostnames_1 + camera_hostnames_2
    ])

    app_detector = NodeApp(
        path=BuiltinApps.DETECTOR,
        params={"cameras": param_cameras},
        http=True)

    node_detector = Node(
        name=f"detector",
        app=app_detector,
        networks=[network_edge_1, network_edge_2, network_cloud])

    mongo = Service(
        name="mongo",
        image="mongo:4",
        restart_policy=RestartPolicy(condition="on-failure"))

    historian_observed_things = [
        {
            "servient_host": f"{node_detector.name}.{network_cloud.name}",
            "thing_id": _THING_ID_DETECTOR
        }
    ]

    historian_app = NodeApp(
        path=BuiltinApps.MONGO_HISTORIAN,
        http=True,
        params={
            "mongo_uri": "mongodb://mongo",
            "observed_things": json.dumps(historian_observed_things)
        })

    node_historian = Node(
        name="cloud",
        app=historian_app,
        networks=[network_cloud, network_cloud_user])

    node_historian.link_service(mongo)

    user_app = NodeApp(
        path=BuiltinApps.CALLER,
        params={
            "servient_host": f"{node_historian.name}.{network_cloud_user.name}",
            "thing_id": _THING_ID_HISTORIAN,
            "params": json.dumps({"write": None, "list": None}),
            "lambd": 5
        })

    node_user = Node(
        name="user",
        app=user_app,
        networks=[network_cloud_user],
        scale=5)

    topology = Topology(nodes=[
        *nodes_camera_1,
        *nodes_camera_2,
        node_detector,
        node_historian,
        node_user
    ])

    return topology
