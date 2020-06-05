import enum


class Labels(enum.Enum):
    WOTEMU_NETWORK = "org.fundacionctic.wotemu.net"
    WOTEMU_GATEWAY = "org.fundacionctic.wotemu.gw"
    WOTEMU_NODE = "org.fundacionctic.wotemu.node"
    WOTEMU_BROKER = "org.fundacionctic.wotemu.broker"


class NetworkConditions(enum.Enum):
    THREEG = "3G"
    WIFI = "WIFI"
    CABLE = "CABLE"


class NodePlatforms(enum.Enum):
    CONSTRAINED = "CONSTRAINED"
    GATEWAY = "LOW_TIER"
    CLOUD = "CLOUD"
    UNCONSTRAINED = "UNCONSTRAINED"
