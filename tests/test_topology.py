import logging
import os
import random
import tempfile
import uuid

import pytest
import sh
from wotemu.config import ConfigVars
from wotemu.topology.models import (Broker, Network, Node, NodeApp,
                                    NodeResources, Topology, TopologyPorts,
                                    TopologyRedis)

_logger = logging.getLogger(__name__)


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
        networks=[network_broker])

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
        compose_res = sh_compose(cmd_config, _err_to_out=True)
        assert compose_res
        _logger.debug("Compose validation result: \n%s", compose_res)
    finally:
        try:
            os.close(temp_fh)
            os.remove(temp_path)
        except:
            pass


def test_topology_ports():
    network = Network(name="my_net")
    node_app = NodeApp(path="/root/app.py", http=True)
    node_one = Node(name="node_one", app=node_app, networks=[network])
    node_two = Node(name="node_two", app=node_app, networks=[network])

    port_http = random.randint(10500, 20000)
    topology_ports = TopologyPorts(http=port_http)

    topology = Topology(
        nodes=[node_one, node_two],
        ports=topology_ports)

    compose = topology.to_compose_dict()
    services = compose.get("services")
    env_one = services.get(node_one.name).get("environment")
    env_two = services.get(node_two.name).get("environment")

    assert env_one == env_two
    assert env_one[ConfigVars.PORT_HTTP.value] == str(port_http)
    assert env_one[ConfigVars.PORT_MQTT.value]


def test_topology_redis():
    network = Network(name="my_net")
    node_app = NodeApp(path="/root/app.py", http=True)
    node = Node(name="node", app=node_app, networks=[network])

    redis_host = uuid.uuid4().hex
    redis_url = "redis://{}".format(redis_host)

    top_redis = TopologyRedis(host=redis_host)
    top = Topology(nodes=[node], redis=top_redis)
    compose = top.to_compose_dict()
    services = compose.get("services")
    node_env = services.get(node.name).get("environment")

    assert redis_host in services
    assert node_env[ConfigVars.REDIS_URL.value] == redis_url

    top_redis_disabled = TopologyRedis(
        host=redis_host,
        enabled=False,
        redis_url=redis_url)

    top_disabled = Topology(nodes=[node], redis=top_redis_disabled)
    compose_disabled = top_disabled.to_compose_dict()
    services_disabled = compose_disabled.get("services")
    node_env_disabled = services_disabled.get(node.name).get("environment")

    assert redis_host not in services_disabled
    assert node_env_disabled[ConfigVars.REDIS_URL.value] == redis_url


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
