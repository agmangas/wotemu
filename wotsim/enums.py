import enum


class Labels(enum.Enum):
    WOTSIM_NETWORK = "org.fundacionctic.wotsim.net"
    WOTSIM_GATEWAY = "org.fundacionctic.wotsim.gw"
    WOTSIM_NODE = "org.fundacionctic.wotsim.node"
    WOTSIM_BROKER = "org.fundacionctic.wotsim.broker"


class NetworkConditions(enum.Enum):
    THREEG = "3G"
    WIFI = "WIFI"
    CABLE = "CABLE"


class NodePlatforms(enum.Enum):
    CONSTRAINED = "CONSTRAINED"
    GATEWAY = "LOW_TIER"
    CLOUD = "CLOUD"
    UNCONSTRAINED = "UNCONSTRAINED"
