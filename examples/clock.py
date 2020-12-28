from wotemu.enums import NetworkConditions
from wotemu.topology.models import (Broker, BuiltinApps, Network, Node,
                                    NodeApp, NodeResources, Topology)

PARAM_SERVIENT_HOST = "servient_host"
PARAM_THING_ID = "thing_id"
THING_ID_CLOCK = "urn:org:fundacionctic:thing:clock"


def topology():
    network_wifi = Network(
        name="wifi",
        conditions=NetworkConditions.WIFI)

    network_2g = Network(
        name="mobile_2g",
        conditions=NetworkConditions.EDGE)

    broker = Broker(
        name="broker",
        networks=[network_2g])

    node_clock_mqtt = Node(
        name="clock_mqtt",
        app=NodeApp(path=BuiltinApps.CLOCK, mqtt=True),
        networks=[network_wifi],
        broker=broker,
        scale=2)

    node_clock_http = Node(
        name="clock_http",
        app=NodeApp(path=BuiltinApps.CLOCK, http=True),
        networks=[network_wifi],
        scale=2)

    host_clock_mqtt = "{}.{}".format(
        node_clock_mqtt.name,
        network_wifi.name)

    app_sub_mqtt = NodeApp(
        path=BuiltinApps.SUBSCRIBER,
        params={
            PARAM_SERVIENT_HOST: host_clock_mqtt,
            PARAM_THING_ID: THING_ID_CLOCK
        })

    host_clock_http = "{}.{}".format(
        node_clock_http.name,
        network_wifi.name)

    app_sub_http = NodeApp(
        path=BuiltinApps.SUBSCRIBER,
        params={
            PARAM_SERVIENT_HOST: host_clock_http,
            PARAM_THING_ID: THING_ID_CLOCK
        })

    sub_resources = NodeResources(
        target_cpu_speed=200,
        mem_limit="200M")

    node_sub_mqtt = Node(
        name="clock_sub_mqtt",
        app=app_sub_mqtt,
        networks=[network_wifi, network_2g],
        resources=sub_resources,
        scale=2)

    node_sub_http = Node(
        name="clock_sub_http",
        app=app_sub_http,
        networks=[network_wifi],
        resources=sub_resources,
        scale=4)

    app_reader = NodeApp(
        path=BuiltinApps.READER,
        params={
            PARAM_SERVIENT_HOST: host_clock_http,
            PARAM_THING_ID: THING_ID_CLOCK
        })

    node_reader = Node(
        name="clock_property_reader",
        app=app_reader,
        networks=[network_wifi],
        scale=2)

    node_error = Node(
        name="clock_error",
        app=NodeApp(path=BuiltinApps.ERROR),
        networks=[network_wifi],
        scale=2)

    topology = Topology(nodes=[
        node_clock_mqtt,
        node_clock_http,
        node_sub_mqtt,
        node_sub_http,
        node_reader,
        node_error
    ])

    return topology
