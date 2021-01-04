from wotemu.enums import NetworkConditions
from wotemu.topology.models import (BuiltinApps, Network, Node, NodeApp,
                                    NodeResources, Topology)

_SERVER_GIST = "https://gist.github.com/agmangas/94cc5c3d9d5dcb473cff774b3522bbb6/raw"


def topology():
    network_3g = Network(
        name="3g",
        conditions=NetworkConditions.REGULAR_3G)

    node_server = Node(
        name="server",
        app=NodeApp(path=_SERVER_GIST, http=True),
        networks=[network_3g],
        scale=1)

    host_server = "{}.{}".format(
        node_server.name,
        network_3g.name)

    app_reader = NodeApp(
        path=BuiltinApps.READER,
        params={
            "servient_host": host_server,
            "thing_id": "urn:wotemu:quickstart:thing"
        })

    node_reader = Node(
        name="reader",
        app=app_reader,
        networks=[network_3g],
        resources=NodeResources(mem_limit="150M"),
        scale=4)

    topology = Topology(nodes=[
        node_server,
        node_reader
    ])

    return topology
