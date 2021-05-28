import enum
import json


class Labels(enum.Enum):
    WOTEMU_NETWORK = "org.fundacionctic.wotemu.net"
    WOTEMU_GATEWAY = "org.fundacionctic.wotemu.gw"
    WOTEMU_NODE = "org.fundacionctic.wotemu.node"
    WOTEMU_BROKER = "org.fundacionctic.wotemu.broker"
    WOTEMU_REDIS = "org.fundacionctic.wotemu.redis"
    WOTEMU_SERVICE = "org.fundacionctic.wotemu.service"
    WOTEMU_SERVICE_NETWORK = "org.fundacionctic.wotemu.servicenet"


class RedisPrefixes(enum.Enum):
    NAMESPACE = "wotemu"
    PACKET = "packet"
    THING = "thing"
    SYSTEM = "system"
    INFO = "info"
    BENCHMARK = "benchmark"
    SNAPSHOT = "snapshot"
    COMPOSE = "compose"
    APP = "app"


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


def _netem(latency=None, jitter=None, rate=None):
    return json.dumps({
        "latency": latency,
        "jitter": jitter,
        "rate": rate
    })


NETEM_CONDITIONS = {
    NetworkConditions.GPRS: [
        _netem(latency=700, jitter=100, rate="50kbit")
    ],
    NetworkConditions.EDGE: [
        _netem(latency=700, jitter=100, rate="100kbit")
    ],
    NetworkConditions.REGULAR_3G: [
        _netem(latency=300, jitter=150, rate="1500kbit")
    ],
    NetworkConditions.FAST_3G: [
        _netem(latency=150, jitter=50, rate="4000kbit")
    ],
    NetworkConditions.LTE: [
        _netem(latency=40, jitter=10, rate="15mbit")
    ],
    NetworkConditions.WIFI: [
        _netem(latency=25, jitter=5, rate="50mbit")
    ],
    NetworkConditions.CABLE: [
        _netem(latency=5, jitter=5, rate="100mbit")
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
    MONGO_HISTORIAN = "wotemu_mongo_historian"
    CAMERA = "wotemu_camera"
    DETECTOR = "wotemu_detector"


BUILTIN_APPS_MODULES = {
    BuiltinApps.CLOCK: "wotemu.apps.clock",
    BuiltinApps.ERROR: "wotemu.apps.error",
    BuiltinApps.READER: "wotemu.apps.reader",
    BuiltinApps.SUBSCRIBER: "wotemu.apps.subscriber",
    BuiltinApps.WORKER: "wotemu.apps.worker",
    BuiltinApps.CALLER: "wotemu.apps.caller",
    BuiltinApps.MONGO_HISTORIAN: "wotemu.apps.historian",
    BuiltinApps.CAMERA: "wotemu.apps.camera",
    BuiltinApps.DETECTOR: "wotemu.apps.detector"
}

assert set(BUILTIN_APPS_MODULES.keys()) == set(BuiltinApps)
