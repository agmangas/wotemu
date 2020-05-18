import collections

from wotsim.enums import NetworkConditions, NodePlatforms


class NodeResources:
    """Represents the hardware constraints and resources of a node."""

    def __init__(self, cpu_limit, mem_limit, cpu_reservation=None, mem_reservation=None):
        self.cpu_limit = cpu_limit
        self.mem_limit = mem_limit
        self.cpu_reservation = cpu_reservation
        self.mem_reservation = mem_reservation


class NodeApp:
    """Represents the arguments to run a WoT app in a node."""

    def __init__(self, path, params=None):
        self.path = path
        self.params = params


class Node:
    """Represents an independent node that runs any given user-defined WoT application."""

    @classmethod
    def to_resources(cls, platform):
        if platform not in NodePlatforms:
            raise ValueError("Unknown node platform")

        raise NotImplementedError

    def __init__(self, name, app, networks, resources=None, scale=None, args_compose=None):
        self.name = name
        self.app = app
        self.networks = networks
        self.resources = resources
        self.scale = scale
        self.args_compose = args_compose


class Broker:
    """Represents a MQTT broker."""

    def __init__(self, name, network, args_compose=None):
        self.name = name
        self.network = network
        self.args_compose = args_compose


class Network:
    """Represents a network that may contain multiple nodes. 
    Each network has a predefined set of conditions that determine its performance."""

    @classmethod
    def to_netem(cls, condition):
        if condition not in NetworkConditions:
            raise ValueError("Unknown network condition")

        raise NotImplementedError

    def __init__(self, name, netem, args_compose_net=None, args_compose_gw=None):
        self.name = name
        self.netem = netem
        self.args_compose_net = args_compose_net
        self.args_compose_gw = args_compose_gw
