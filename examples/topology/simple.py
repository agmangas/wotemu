import sys

from wotsim.enums import NetworkConditions
from wotsim.topology.models import Broker, Network, Node, NodeApp, Topology
from wotsim.topology.utils import conditions_to_netem

APP_CLOCK = "/root/wotsim/examples/app/clock.py"
APP_SUBSCRIBER = "/root/wotsim/examples/app/subscriber.py"
PARAM_SERVIENT_HOST = "servient_host"
PARAM_THING_ID = "thing_id"
THING_ID_CLOCK = "urn:org:fundacionctic:thing:clock"


def build_topology():
    network_wifi = Network(
        name="wifi",
        netem=conditions_to_netem(NetworkConditions.WIFI))

    network_3g = Network(
        name="mobile_3g",
        netem=conditions_to_netem(NetworkConditions.THREEG))

    broker = Broker(
        name="broker",
        networks=[network_3g])

    node_clock = Node(
        name="clock",
        app=NodeApp(path=APP_CLOCK, http=True, mqtt=True),
        networks=[network_wifi],
        broker=broker)

    host_clock = "{}.{}".format(
        node_clock.name,
        network_wifi.name)

    app_sub = NodeApp(
        path=APP_SUBSCRIBER,
        params={
            PARAM_SERVIENT_HOST: host_clock,
            PARAM_THING_ID: THING_ID_CLOCK
        })

    node_sub = Node(
        name="clock_sub",
        app=app_sub,
        networks=[network_wifi, network_3g],
        scale=3)

    topology = Topology(nodes=[node_clock, node_sub])

    return topology


if __name__ == "__main__":
    topology = build_topology()

    if len(sys.argv) < 2:
        print("First argument should be the output file path")
        sys.exit(0)

    compose_path = sys.argv[1]
    print("Writing Compose file to: {}".format(compose_path))

    with open(compose_path, "w") as fh:
        fh.write(topology.to_compose_yaml())
