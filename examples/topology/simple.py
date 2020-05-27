import sys

from wotsim.topology.models import Broker, Network, Node, NodeApp, Topology

APP_CLOCK = "/root/wotsim/examples/app/clock.py"
APP_SUBSCRIBER = "/root/wotsim/examples/app/subscriber.py"
PARAM_SERVIENT_HOST = "servient_host"
PARAM_THING_ID = "thing_id"
THING_ID_CLOCK = "urn:org:fundacionctic:thing:clock"


def build_topology():
    network_cable = Network(
        name="cable",
        netem=["delay --time 5 --jitter 1 --distribution normal"])

    network_wifi = Network(
        name="wifi",
        netem=["delay --time 15 --jitter 10 --distribution normal"])

    network_3g = Network(
        name="mobile_3g",
        netem=[
            "delay --time 100 --jitter 50 --distribution normal",
            "rate --rate 200kbit"
        ])

    broker = Broker(name="broker", networks=[network_3g])

    node_cable = Node(
        name="node_cable",
        app=NodeApp(path=APP_CLOCK, ws=True),
        networks=[network_cable])

    node_wifi_cable = Node(
        name="node_wifi_cable",
        app=NodeApp(path=APP_CLOCK, mqtt=True),
        networks=[network_wifi, network_cable, network_3g],
        broker=broker,
        broker_network=network_3g)

    node_wifi_1 = Node(
        name="node_wifi_1",
        app=NodeApp(path=APP_CLOCK, http=True, coap=True),
        networks=[network_wifi])

    node_wifi_cable_host = "{}.{}".format(
        node_wifi_cable.name,
        network_wifi.name)

    app_wifi_2 = NodeApp(
        path=APP_SUBSCRIBER,
        params={
            PARAM_SERVIENT_HOST: node_wifi_cable_host,
            PARAM_THING_ID: THING_ID_CLOCK
        })

    node_wifi_2 = Node(
        name="node_wifi_2",
        app=app_wifi_2,
        networks=[network_wifi, network_3g])

    topology = Topology(
        nodes=[node_wifi_1, node_wifi_2, node_cable, node_wifi_cable])

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
