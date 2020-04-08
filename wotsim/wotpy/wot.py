import logging
import os

import wotpy.wot.servient
import wotpy.wot.td
import wotpy.wot.wot
from wotpy.protocols.http.server import HTTPServer
from wotpy.protocols.mqtt.server import MQTTServer
from wotpy.protocols.ws.server import WebsocketServer

from wotsim.wotpy.things import ConsumedThing, ExposedThing

_ENV_PORT_HTTP = "PORT_HTTP"
_ENV_PORT_WS = "PORT_WS"
_ENV_PORT_COAP = "PORT_COAP"
_ENV_MQTT_BROKER = "MQTT_BROKER"

_logger = logging.getLogger(__name__)


class WoT(wotpy.wot.wot.WoT):
    def __init__(self, *args, **kwargs):
        self.exposed_cb = kwargs.pop("exposed_cb", None)
        self.consumed_cb = kwargs.pop("consumed_cb", None)
        super().__init__(*args, **kwargs)

    def consume(self, td_str):
        td = wotpy.wot.td.ThingDescription(td_str)

        return ConsumedThing(
            servient=self._servient,
            td=td,
            deco_cb=self.consumed_cb)

    def produce(self, model):
        thing = self.thing_from_model(model)

        exposed_thing = ExposedThing(
            servient=self._servient,
            thing=thing,
            deco_cb=self.exposed_cb)

        self._servient.add_exposed_thing(exposed_thing)
        return exposed_thing


def _build_http_server(port=None):
    try:
        port = int(port if port else os.getenv(_ENV_PORT_HTTP, None))
    except Exception:
        return None

    _logger.debug("Creating HTTP server on: %s", port)
    return HTTPServer(port=int(port))


def _build_ws_server(port=None):
    try:
        port = int(port if port else os.getenv(_ENV_PORT_WS, None))
    except Exception:
        return None

    _logger.debug("Creating WebSockets server on: %s", port)
    return WebsocketServer(port=int(port))


def _build_coap_server(port=None):
    try:
        port = int(port if port else os.getenv(_ENV_PORT_COAP, None))
    except Exception:
        return None

    try:
        from wotpy.protocols.coap.server import CoAPServer
        _logger.debug("Creating CoAP server on: %s", port)
        return CoAPServer(port=int(port))
    except NotImplementedError as ex:
        _logger.warning(ex)


def _build_mqtt_server(servient_id, broker=None):
    broker = broker if broker else os.getenv(_ENV_MQTT_BROKER, None)

    if not broker:
        return None

    _logger.debug("Creating MQTT server on: %s", broker)
    return MQTTServer(broker, servient_id=servient_id)


def wot_entrypoint(
        port_catalogue=9090, hostname=None, exposed_cb=None, consumed_cb=None,
        port_http=None, port_ws=None, port_coap=None, mqtt_url=None):
    servient = wotpy.wot.servient.Servient(
        hostname=hostname,
        catalogue_port=port_catalogue)

    http_server = _build_http_server(port=port_http)
    ws_server = _build_ws_server(port=port_ws)
    coap_server = _build_coap_server(port=port_coap)

    mqtt_server = _build_mqtt_server(
        servient_id=servient.hostname,
        broker=mqtt_url)

    servers = [http_server, ws_server, coap_server, mqtt_server]
    servers = [item for item in servers if item]
    _logger.debug("Adding servers (%s) to servient (%s)", servers, servient)
    [servient.add_server(item) for item in servers]

    return WoT(
        servient=servient,
        exposed_cb=exposed_cb,
        consumed_cb=consumed_cb)