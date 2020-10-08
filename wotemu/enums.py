import enum


class Labels(enum.Enum):
    WOTEMU_NETWORK = "org.fundacionctic.wotemu.net"
    WOTEMU_GATEWAY = "org.fundacionctic.wotemu.gw"
    WOTEMU_NODE = "org.fundacionctic.wotemu.node"
    WOTEMU_BROKER = "org.fundacionctic.wotemu.broker"


class RedisPrefixes(enum.Enum):
    NAMESPACE = "wotemu"
    PACKET = "packet"
    THING = "thing"
    SYSTEM = "system"
    INFO = "info"
    BENCHMARK = "benchmark"


class NetworkConditions(enum.Enum):
    THREEG = "3G"
    WIFI = "WIFI"
    CABLE = "CABLE"


class NodePlatforms(enum.Enum):
    CONSTRAINED = "CONSTRAINED"
    GATEWAY = "GATEWAY"
    CLOUD = "CLOUD"
    UNCONSTRAINED = "UNCONSTRAINED"


NETEM_CONDITIONS = {
    NetworkConditions.THREEG: [
        "delay --time 100 --jitter 50 --distribution normal",
        "rate --rate 200kbit"
    ],
    NetworkConditions.WIFI: [
        "delay --time 15 --jitter 10 --distribution normal"
    ],
    NetworkConditions.CABLE: [
        "delay --time 5 --jitter 1 --distribution normal"
    ]
}

assert set(NETEM_CONDITIONS.keys()) == set(NetworkConditions)
