import os
import tempfile

import pytest
import sh

from wotsim.topology.models import (Broker, Network, Node, NodeApp,
                                    NodeResources, Topology)


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

    node_resources = NodeResources(
        cpu_limit=0.5,
        mem_limit="100M",
        mem_reservation="50M")

    node = Node(
        name="the_node",
        app=node_app,
        networks=[network],
        broker=broker,
        resources=node_resources)

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


def test_topology_compose(topology):
    assert topology.to_compose_dict()


def test_topology_compose_yaml(topology):
    try:
        sh_compose = sh.Command("docker-compose")
    except sh.CommandNotFound:
        pytest.skip("Compose CLI is not available")
        return

    try:
        temp_fh, temp_path = tempfile.mkstemp(suffix=".yml")

        with open(temp_path, "w") as fh:
            fh.write(topology.to_compose_yaml())

        cmd_config = ["-f", temp_path, "config"]
        assert sh_compose(cmd_config, _err_to_out=True)
    finally:
        try:
            os.close(temp_fh)
            os.remove(temp_path)
        except:
            pass


def test_node_compose(topology):
    node = topology.nodes[0]
    assert node.to_compose_dict(topology)


def test_broker_compose(topology):
    broker = topology.brokers[0]
    assert broker.to_compose_dict(topology)


def test_network_compose(topology):
    network = topology.networks[0]
    assert network.to_compose_dict(topology)


def test_network_gateway_compose(topology):
    network = topology.networks[0]
    assert network.to_gateway_compose_dict(topology)
