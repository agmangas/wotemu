import json

from docker.types import RestartPolicy
from wotemu.enums import NetworkConditions
from wotemu.topology.models import (BuiltinApps, Network, Node, NodeApp,
                                    Service, Topology)


def topology():
    network_wifi = Network(
        name="wifi",
        conditions=NetworkConditions.WIFI)

    mongo = Service(
        name="mongo",
        image="mongo:4",
        restart_policy=RestartPolicy(condition="on-failure"))

    nodes_clock = [
        Node(
            name=f"clock_{idx}",
            app=NodeApp(path=BuiltinApps.CLOCK, ws=True),
            networks=[network_wifi])
        for idx in range(5)
    ]

    observed_things = [
        {
            "servient_host": f"{item.name}.{network_wifi.name}",
            "thing_id": "urn:org:fundacionctic:thing:clock"
        }
        for item in nodes_clock
    ]

    historian_app = NodeApp(
        path=BuiltinApps.MONGO_HISTORIAN,
        http=True,
        params={
            "mongo_uri": "mongodb://mongo",
            "observed_things": json.dumps(observed_things)
        })

    node_historian = Node(
        name="historian",
        app=historian_app,
        networks=[network_wifi])

    node_historian.link_service(mongo)

    topology = Topology(nodes=[
        *nodes_clock,
        node_historian
    ])

    return topology
