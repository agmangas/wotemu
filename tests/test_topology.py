import pytest

from wotsim.topology.models import Broker, Network, Node, NodeApp, Topology


@pytest.fixture
def topology():
    network = Network(
        name="the_net",
        netem=["delay --time 15 --jitter 10 --distribution normal"])

    network_broker = Network(
        name="the_broker_net",
        netem=["delay --time 100 --jitter 50 --distribution normal"])

    node_app = NodeApp(
        path="/root/app.py",
        http=True,
        mqtt=True,
        params={"one": 1, "hello": "world"})

    broker = Broker(
        name="the_broker",
        network=network_broker)

    node = Node(
        name="the_node",
        app=node_app,
        networks=[network],
        broker=broker)

    return Topology(nodes=[node])


def test_names_underscore(topology):
    node = topology.nodes[0]

    node_kwargs = {
        "app": node.app,
        "networks": node.networks,
        "broker": node.broker
    }

    name_bad = "badName"
    node_bad = Node(name=name_bad, **node_kwargs)

    assert node_bad.name != name_bad

    name_ok = "ok_name"
    node_ok = Node(name=name_ok, **node_kwargs)

    assert node_ok.name == name_ok


def test_node_compose(topology):
    node = topology.nodes[0]
    assert node.to_compose_dict(topology)


def test_broker_compose(topology):
    broker = topology.brokers[0]
    assert broker.to_compose_dict(topology)


def test_network_gateway_compose(topology):
    network = topology.networks[0]
    assert network.to_gateway_compose_dict(topology)
