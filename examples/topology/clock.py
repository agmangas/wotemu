from wotemu.enums import NetworkConditions
from wotemu.topology.models import Broker, Network, Node, NodeApp, Topology

APP_CLOCK = "/root/wotemu/examples/app/clock.py"
APP_SUBSCRIBER = "/root/wotemu/examples/app/subscriber.py"
PARAM_SERVIENT_HOST = "servient_host"
PARAM_THING_ID = "thing_id"
THING_ID_CLOCK = "urn:org:fundacionctic:thing:clock"


def topology():
    network_wifi = Network(
        name="wifi",
        conditions=NetworkConditions.WIFI)

    network_3g = Network(
        name="mobile_3g",
        conditions=NetworkConditions.THREEG)

    broker = Broker(
        name="broker",
        networks=[network_3g])

    node_clock = Node(
        name="clock",
        app=NodeApp(path=APP_CLOCK, http=True, mqtt=True),
        networks=[network_wifi],
        broker=broker,
        scale=2)

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
        scale=4)

    topology = Topology(nodes=[node_clock, node_sub])

    return topology