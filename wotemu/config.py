import collections
import enum
import logging
import os
import pprint

DEFAULT_DOCKER_SOCKET = "/var/run/docker.sock"
DEFAULT_HOST_REDIS = "redis"
DEFAULT_HOST_DOCKER_PROXY = "docker_api_proxy"

_DEFAULT_PORT_CATALOGUE = 9090
_DEFAULT_PORT_HTTP = 80
_DEFAULT_PORT_WS = 81
_DEFAULT_PORT_COAP = 5683
_DEFAULT_PORT_MQTT = 1883
_DEFAULT_REDIS_URL = "redis://{}".format(DEFAULT_HOST_REDIS)
_DEFAULT_DOCKER_PROXY_URL = "tcp://{}:2375/".format(DEFAULT_HOST_DOCKER_PROXY)

_logger = logging.getLogger(__name__)


EnvConfig = collections.namedtuple(
    "EnvConfig",
    [
        "port_catalogue",
        "port_http",
        "port_coap",
        "port_ws",
        "port_mqtt",
        "mqtt_broker_host",
        "mqtt_url",
        "redis_url",
        "docker_proxy_url",
        "other_ports_tcp",
        "other_ports_udp"
    ])


class ConfigVars(enum.Enum):
    PORT_CATALOGUE = "PORT_CATALOGUE"
    PORT_HTTP = "PORT_HTTP"
    PORT_WS = "PORT_WS"
    PORT_COAP = "PORT_COAP"
    PORT_MQTT = "PORT_MQTT"
    MQTT_BROKER_HOST = "MQTT_BROKER_HOST"
    REDIS_URL = "REDIS_URL"
    DOCKER_PROXY_URL = "DOCKER_PROXY_URL"
    OTHER_PORTS_TCP = "OTHER_PORTS_TCP"
    OTHER_PORTS_UDP = "OTHER_PORTS_UDP"


DEFAULT_CONFIG_VARS = {
    ConfigVars.PORT_CATALOGUE: _DEFAULT_PORT_CATALOGUE,
    ConfigVars.PORT_HTTP: _DEFAULT_PORT_HTTP,
    ConfigVars.PORT_WS: _DEFAULT_PORT_WS,
    ConfigVars.PORT_COAP: _DEFAULT_PORT_COAP,
    ConfigVars.PORT_MQTT: _DEFAULT_PORT_MQTT,
    ConfigVars.MQTT_BROKER_HOST: None,
    ConfigVars.REDIS_URL: _DEFAULT_REDIS_URL,
    ConfigVars.DOCKER_PROXY_URL: _DEFAULT_DOCKER_PROXY_URL,
    ConfigVars.OTHER_PORTS_TCP: None,
    ConfigVars.OTHER_PORTS_UDP: None
}


def _getenv_int(name, default):
    try:
        return int(os.getenv(name, default))
    except:
        _logger.warning(
            "Unexpected int value (%s) in variable %s: Using default (%s)",
            os.getenv(name), name, default)

        return default


def _parse_ports(val):
    try:
        return [int(item) for item in val.split(",")]
    except:
        _logger.warning(f"Error parsing ports: {val}", exc_info=True)
        return None


def get_env_config():
    port_catalogue = _getenv_int(
        ConfigVars.PORT_CATALOGUE.value,
        DEFAULT_CONFIG_VARS.get(ConfigVars.PORT_CATALOGUE))

    port_http = _getenv_int(
        ConfigVars.PORT_HTTP.value,
        DEFAULT_CONFIG_VARS.get(ConfigVars.PORT_HTTP))

    port_ws = _getenv_int(
        ConfigVars.PORT_WS.value,
        DEFAULT_CONFIG_VARS.get(ConfigVars.PORT_WS))

    port_coap = _getenv_int(
        ConfigVars.PORT_COAP.value,
        DEFAULT_CONFIG_VARS.get(ConfigVars.PORT_COAP))

    port_mqtt = _getenv_int(
        ConfigVars.PORT_MQTT.value,
        DEFAULT_CONFIG_VARS.get(ConfigVars.PORT_MQTT))

    mqtt_broker_host = os.getenv(
        ConfigVars.MQTT_BROKER_HOST.value,
        DEFAULT_CONFIG_VARS.get(ConfigVars.MQTT_BROKER_HOST))

    redis_url = os.getenv(
        ConfigVars.REDIS_URL.value,
        DEFAULT_CONFIG_VARS.get(ConfigVars.REDIS_URL))

    docker_proxy_url = os.getenv(
        ConfigVars.DOCKER_PROXY_URL.value,
        DEFAULT_CONFIG_VARS.get(ConfigVars.DOCKER_PROXY_URL))

    other_ports_tcp = os.getenv(
        ConfigVars.OTHER_PORTS_TCP.value,
        DEFAULT_CONFIG_VARS.get(ConfigVars.OTHER_PORTS_TCP))

    other_ports_udp = os.getenv(
        ConfigVars.OTHER_PORTS_UDP.value,
        DEFAULT_CONFIG_VARS.get(ConfigVars.OTHER_PORTS_UDP))

    other_ports_tcp = other_ports_tcp and _parse_ports(other_ports_tcp)
    other_ports_udp = other_ports_udp and _parse_ports(other_ports_udp)

    mqtt_url = None

    if port_mqtt and mqtt_broker_host:
        mqtt_url = "mqtt://{}:{}".format(mqtt_broker_host, port_mqtt)

    config = EnvConfig(
        port_catalogue=port_catalogue,
        port_http=port_http,
        port_ws=port_ws,
        port_coap=port_coap,
        port_mqtt=port_mqtt,
        mqtt_broker_host=mqtt_broker_host,
        mqtt_url=mqtt_url,
        redis_url=redis_url,
        docker_proxy_url=docker_proxy_url,
        other_ports_tcp=other_ports_tcp,
        other_ports_udp=other_ports_udp)

    return config


def log_config():
    conf_env = {key.value: os.getenv(key.value, None) for key in ConfigVars}
    _logger.debug("Configuration environment:\n%s", pprint.pformat(conf_env))
    _logger.debug("Current configuration: %s", get_env_config())
