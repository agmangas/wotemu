import collections
import logging
import warnings

import inflection
import yaml

from wotsim.config import (DEFAULT_CONFIG_VARS, DEFAULT_HOST_DOCKER_PROXY,
                           DEFAULT_HOST_REDIS, ConfigVars)
from wotsim.enums import NetworkConditions, NodePlatforms
from wotsim.topology.compose import (BASE_IMAGE, get_broker_definition,
                                     get_docker_proxy_definition,
                                     get_network_definition,
                                     get_network_gateway_definition,
                                     get_node_definition, get_redis_definition,
                                     get_topology_definition)

_DEFAULT_CATALOGUE = DEFAULT_CONFIG_VARS[ConfigVars.PORT_CATALOGUE]
_DEFAULT_HTTP = DEFAULT_CONFIG_VARS[ConfigVars.PORT_HTTP]
_DEFAULT_WS = DEFAULT_CONFIG_VARS[ConfigVars.PORT_WS]
_DEFAULT_MQTT = DEFAULT_CONFIG_VARS[ConfigVars.PORT_MQTT]
_DEFAULT_COAP = DEFAULT_CONFIG_VARS[ConfigVars.PORT_COAP]

_logger = logging.getLogger(__name__)


class NodeResources:
    """Represents the hardware constraints and resources of a node."""

    def __init__(self, cpu_limit, mem_limit, cpu_reservation=None, mem_reservation=None):
        if cpu_reservation is not None:
            cpu_reservation = str(cpu_reservation)

        if mem_reservation is not None:
            mem_reservation = str(mem_reservation)

        self.cpu_limit = str(cpu_limit)
        self.mem_limit = str(mem_limit)
        self.cpu_reservation = cpu_reservation
        self.mem_reservation = mem_reservation


class NodeApp:
    """Represents the arguments to run a WoT app in a node."""

    ARG_PATH = "--path"
    ARG_PARAM = "--func-param"
    ARG_HTTP = "--enable-http"
    ARG_WS = "--enable-ws"
    ARG_MQTT = "--enable-mqtt"
    ARG_COAP = "--enable-coap"

    def __init__(self, path, http=False, ws=False, mqtt=False, coap=False, params=None):
        self.path = path
        self.params = params if params else {}
        self._http = http
        self._ws = ws
        self._mqtt = mqtt
        self._coap = coap

    @property
    def app_args(self):
        parts = [self.ARG_PATH, self.path]

        for key, val in self.params.items():
            parts += [self.ARG_PARAM, str(key), str(val)]

        protocol_flags = [
            (self.enabled_http, self.ARG_HTTP),
            (self.enabled_ws, self.ARG_WS),
            (self.enabled_mqtt, self.ARG_MQTT),
            (self.enabled_coap, self.ARG_COAP)
        ]

        parts += [flag for enabled, flag in protocol_flags if enabled]

        return parts

    @property
    def enabled_http(self):
        return bool(self._http)

    @property
    def enabled_ws(self):
        return bool(self._ws)

    @property
    def enabled_mqtt(self):
        return bool(self._mqtt)

    @property
    def enabled_coap(self):
        return bool(self._coap)


class BaseNamedModel:
    """Base class of all models with a unique name."""

    def __init__(self, name):
        name_clean = inflection.underscore(name)

        if name != name_clean:
            _logger.warning("Converted name '%s' to '%s'", name, name_clean)

        self._name = name_clean

    def __eq__(self, other):
        self.name == other.name

    def __hash__(self):
        return hash(self.name)

    @property
    def name(self):
        return self._name


class Node(BaseNamedModel):
    """Represents an independent node that runs any given user-defined WoT application."""

    ENTRY_APP = "app"

    @classmethod
    def to_resources(cls, platform):
        if platform not in NodePlatforms:
            raise ValueError("Unknown node platform")

        raise NotImplementedError

    def __init__(
            self, name, app, networks, broker=None, broker_network=None,
            image=BASE_IMAGE, resources=None, scale=None, args_compose=None):
        if app.enabled_mqtt and not broker:
            raise ValueError("A broker should be defined when MQTT is enabled")

        if broker and broker_network and broker_network not in broker.networks:
            raise ValueError("Broker network {} is not linked to broker {}".format(
                broker_network, broker))

        self.app = app
        self.networks = networks
        self.broker = broker
        self._broker_network = broker_network
        self.image = image
        self.resources = resources
        self.scale = scale
        self.args_compose = args_compose
        super().__init__(name)

    @property
    def broker_network(self):
        if not self.broker:
            return None

        if self._broker_network:
            assert self._broker_network in self.broker.networks
            return self._broker_network

        return self.broker.networks[0]

    @property
    def broker_host(self):
        if not self.broker:
            return None

        return "{}.{}".format(self.broker.name, self.broker_network.name)

    @property
    def cmd_app(self):
        return [self.ENTRY_APP] + list(self.app.app_args)

    def to_compose_dict(self, topology):
        return get_node_definition(topology, self)


class Broker(BaseNamedModel):
    """Represents a MQTT broker."""

    def __init__(self, name, networks, args_compose=None):
        self.networks = networks
        self.args_compose = args_compose
        super().__init__(name)

    def to_compose_dict(self, topology):
        return get_broker_definition(topology, self)


class Network(BaseNamedModel):
    """Represents a network that may contain multiple nodes. 
    Each network has a predefined set of conditions that determine its performance."""

    GATEWAY_PREFIX = "gw"
    assert inflection.underscore(GATEWAY_PREFIX) == GATEWAY_PREFIX
    ENTRY_GATEWAY = "gateway"

    @classmethod
    def to_netem(cls, condition):
        if condition not in NetworkConditions:
            raise ValueError("Unknown network condition")

        raise NotImplementedError

    def __init__(self, name, netem=None, args_compose_net=None, args_compose_gw=None):
        self._netem = netem
        self.args_compose_net = args_compose_net
        self.args_compose_gw = args_compose_gw
        super().__init__(name)

    @property
    def name_gateway(self):
        return "{}_{}".format(self.GATEWAY_PREFIX, self.name)

    @property
    def netem_args(self):
        return self._netem if self._netem else []

    @property
    def cmd_gateway(self):
        return [self.ENTRY_GATEWAY] + list(self.netem_args)

    def to_compose_dict(self, topology):
        return get_network_definition(topology, self)

    def to_gateway_compose_dict(self, topology):
        return get_network_gateway_definition(topology, self)


class TopologyPorts:
    def __init__(
            self, catalogue=_DEFAULT_CATALOGUE, http=_DEFAULT_HTTP,
            ws=_DEFAULT_WS, mqtt=_DEFAULT_MQTT, coap=_DEFAULT_COAP):
        self.catalogue = catalogue
        self.http = http
        self.ws = ws
        self.mqtt = mqtt
        self.coap = coap

    @property
    def config(self):
        return {
            ConfigVars.PORT_CATALOGUE.value: self.catalogue,
            ConfigVars.PORT_HTTP.value: self.http,
            ConfigVars.PORT_WS.value: self.ws,
            ConfigVars.PORT_MQTT.value: self.mqtt,
            ConfigVars.PORT_COAP.value: self.coap
        }


class TopologyRedis:
    WARN_MSG = "Disabled built-in topology Redis service"

    def __init__(self, enabled=True, host=DEFAULT_HOST_REDIS):
        self.enabled = bool(enabled)
        self.host = host

        if not self.enabled:
            warnings.warn(self.WARN_MSG, Warning)

    @property
    def config(self):
        redis_url = "redis://{}".format(self.host)
        return {ConfigVars.REDIS_URL.value: redis_url}

    def to_compose_dict(self, topology):
        return get_redis_definition(topology)


class TopologyDockerProxy:
    WARN_MSG = "Disabled built-in topology Docker API Proxy service"

    def __init__(self, enabled=True, host=DEFAULT_HOST_DOCKER_PROXY):
        self.enabled = bool(enabled)
        self.host = host

        if not self.enabled:
            warnings.warn(self.WARN_MSG, Warning)

    @property
    def config(self):
        docker_url = "tcp://{}:2375/".format(self.host)
        return {ConfigVars.DOCKER_PROXY_URL.value: docker_url}

    def to_compose_dict(self, topology):
        return get_docker_proxy_definition(topology)


class Topology:
    """Represents a topology consisting of a set of 
    Nodes and Brokers iterconnected by Networks."""

    def __init__(self, nodes, ports=None, redis=None, docker_proxy=None, brokers=None):
        self.nodes = nodes
        self.ports = ports if ports else TopologyPorts()
        self.redis = redis if redis else TopologyRedis()
        self.docker_proxy = docker_proxy if docker_proxy else TopologyDockerProxy()
        self._brokers = brokers

    @property
    def config(self):
        return {
            **self.ports.config,
            **self.redis.config,
            **self.docker_proxy.config
        }

    @property
    def redis_compose_dict(self):
        return self.redis.to_compose_dict(self)

    @property
    def docker_proxy_compose_dict(self):
        return self.docker_proxy.to_compose_dict(self)

    @property
    def brokers(self):
        brokers = self._brokers if self._brokers else []
        brokers += [node.broker for node in self.nodes if node.broker]
        return list(set(brokers))

    @property
    def networks(self):
        nets_node = set([net for node in self.nodes for net in node.networks])
        nets_brkr = set([net for brk in self.brokers for net in brk.networks])
        return list(nets_node.union(nets_brkr))

    def to_compose_dict(self):
        return get_topology_definition(self)

    def to_compose_yaml(self):
        return yaml.dump(self.to_compose_dict())
