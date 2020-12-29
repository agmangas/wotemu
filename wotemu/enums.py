import enum


class Labels(enum.Enum):
    WOTEMU_NETWORK = "org.fundacionctic.wotemu.net"
    WOTEMU_GATEWAY = "org.fundacionctic.wotemu.gw"
    WOTEMU_NODE = "org.fundacionctic.wotemu.node"
    WOTEMU_BROKER = "org.fundacionctic.wotemu.broker"
    WOTEMU_REDIS = "org.fundacionctic.wotemu.redis"


class RedisPrefixes(enum.Enum):
    NAMESPACE = "wotemu"
    PACKET = "packet"
    THING = "thing"
    SYSTEM = "system"
    INFO = "info"
    BENCHMARK = "benchmark"
    SNAPSHOT = "snapshot"
    COMPOSE = "compose"


class NetworkConditions(enum.Enum):
    GPRS = "GPRS"
    EDGE = "EDGE"
    REGULAR_3G = "REGULAR_3G"
    FAST_3G = "FAST_3G"
    LTE = "LTE"
    WIFI = "WIFI"
    CABLE = "CABLE"


class NodePlatforms(enum.Enum):
    CONSTRAINED = "CONSTRAINED"
    GATEWAY = "GATEWAY"
    CLOUD = "CLOUD"
    UNCONSTRAINED = "UNCONSTRAINED"


_DELAY = "delay --time {latency} --jitter {jitter} --distribution normal"
_RATE = "rate --rate {rate}"

NETEM_CONDITIONS = {
    NetworkConditions.GPRS: [
        _DELAY.format(latency=700, jitter=100),
        _RATE.format(rate="50kbit")
    ],
    NetworkConditions.EDGE: [
        _DELAY.format(latency=700, jitter=100),
        _RATE.format(rate="100kbit")
    ],
    NetworkConditions.REGULAR_3G: [
        _DELAY.format(latency=300, jitter=150),
        _RATE.format(rate="1500kbit")
    ],
    NetworkConditions.FAST_3G: [
        _DELAY.format(latency=150, jitter=50),
        _RATE.format(rate="4000kbit")
    ],
    NetworkConditions.LTE: [
        _DELAY.format(latency=40, jitter=10),
        _RATE.format(rate="15mbit")
    ],
    NetworkConditions.WIFI: [
        _DELAY.format(latency=25, jitter=5),
        _RATE.format(rate="50mbit")
    ],
    NetworkConditions.CABLE: [
        _DELAY.format(latency=5, jitter=5),
        _RATE.format(rate="100mbit")
    ]
}

assert set(NETEM_CONDITIONS.keys()) == set(NetworkConditions)


class BuiltinApps(enum.Enum):
    CLOCK = "wotemu_clock"
    ERROR = "wotemu_error"
    READER = "wotemu_reader"
    SUBSCRIBER = "wotemu_subscriber"
    WORKER = "wotemu_worker"
    CALLER = "wotemu_caller"


BUILTIN_APPS_MODULES = {
    BuiltinApps.CLOCK: "wotemu.apps.clock",
    BuiltinApps.ERROR: "wotemu.apps.error",
    BuiltinApps.READER: "wotemu.apps.reader",
    BuiltinApps.SUBSCRIBER: "wotemu.apps.subscriber",
    BuiltinApps.WORKER: "wotemu.apps.worker",
    BuiltinApps.CALLER: "wotemu.apps.caller"
}

assert set(BUILTIN_APPS_MODULES.keys()) == set(BuiltinApps)
