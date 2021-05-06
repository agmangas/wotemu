import json

from docker.types import RestartPolicy
from wotemu.enums import NetworkConditions
from wotemu.topology.models import (BuiltinApps, Network, Node, NodeApp,
                                    NodeResources, Service, Topology)

_ID_1 = "location_1"
_ID_2 = "location_2"

_THING_ID_DETECTOR = "urn:org:fundacionctic:thing:wotemu:detector"
_THING_ID_HISTORIAN = "urn:org:fundacionctic:thing:historian"


def _build_detector_cluster(
        cluster_id, network_edge, num_cameras,
        camera_resources=None, detector_resources=None):
    network = Network(
        name=f"field_{cluster_id}",
        conditions=NetworkConditions.WIFI)

    nodes_camera = [
        Node(
            name=f"camera_{cluster_id}_{idx}",
            app=NodeApp(path=BuiltinApps.CAMERA, http=True),
            networks=[network],
            resources=camera_resources)
        for idx in range(num_cameras)
    ]

    camera_hostnames = [
        f"{item.name}.{network.name}"
        for item in nodes_camera
    ]

    param_cameras = json.dumps([
        {"servient_host": cam_name}
        for cam_name in camera_hostnames
    ])

    app_detector = NodeApp(
        path=BuiltinApps.DETECTOR,
        params={"cameras": param_cameras},
        http=True)

    node_detector = Node(
        name=f"detector_{cluster_id}",
        app=app_detector,
        networks=[network, network_edge],
        resources=detector_resources)

    return nodes_camera, node_detector


def topology():
    network_edge_1 = Network(
        name=f"edge_link_{_ID_1}",
        conditions=NetworkConditions.REGULAR_3G)

    network_edge_2 = Network(
        name=f"edge_link_{_ID_2}",
        conditions=NetworkConditions.REGULAR_3G)

    network_cloud_user = Network(
        name="cloud_user",
        conditions=NetworkConditions.CABLE)

    camera_resources = NodeResources(
        target_cpu_speed=200,
        mem_limit="256M")

    detector_resources = NodeResources(
        target_cpu_speed=600,
        mem_limit="1G")

    nodes_camera_1, node_detector_1 = _build_detector_cluster(
        cluster_id=_ID_1,
        network_edge=network_edge_1,
        num_cameras=3,
        camera_resources=camera_resources,
        detector_resources=detector_resources)

    nodes_camera_2, node_detector_2 = _build_detector_cluster(
        cluster_id=_ID_2,
        network_edge=network_edge_2,
        num_cameras=1,
        camera_resources=camera_resources,
        detector_resources=detector_resources)

    mongo = Service(
        name="mongo",
        image="mongo:4",
        restart_policy=RestartPolicy(condition="on-failure"))

    historian_observed_things = [
        {
            "servient_host": f"{node_detector_1.name}.{network_edge_1.name}",
            "thing_id": _THING_ID_DETECTOR
        },
        {
            "servient_host": f"{node_detector_2.name}.{network_edge_2.name}",
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
        name="historian",
        app=historian_app,
        networks=[network_edge_1, network_edge_2, network_cloud_user])

    node_historian.link_service(mongo)

    user_app = NodeApp(
        path=BuiltinApps.CALLER,
        params={
            "servient_host": f"{node_historian.name}.{network_cloud_user.name}",
            "thing_id": _THING_ID_HISTORIAN,
            "params": json.dumps({"write": None}),
            "lambd": 3
        })

    node_user = Node(
        name="user",
        app=user_app,
        networks=[network_cloud_user],
        scale=3)

    topology = Topology(nodes=[
        *nodes_camera_1,
        node_detector_1,
        *nodes_camera_2,
        node_detector_2,
        node_historian,
        node_user
    ])

    return topology
