import logging
import os

import wotpy.wot.servient
import wotpy.wot.td
import wotpy.wot.wot
from wotpy.protocols.http.server import HTTPServer
from wotpy.protocols.mqtt.server import MQTTServer
from wotpy.protocols.ws.server import WebsocketServer

from wotemu.wotpy.things import ConsumedThing, ExposedThing

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


def wot_entrypoint(
        port_catalogue=9090, hostname=None, exposed_cb=None, consumed_cb=None,
        port_http=None, port_ws=None, port_coap=None, mqtt_url=None):
    servient = wotpy.wot.servient.Servient(
        hostname=hostname,
        catalogue_port=port_catalogue)

    servers = []

    if port_http:
        _logger.debug("Creating HTTP server on port: %s", port_http)
        servers.append(HTTPServer(port=port_http))

    if port_ws:
        _logger.debug("Creating Websocket server on port: %s", port_ws)
        servers.append(WebsocketServer(port=port_ws))

    if port_coap:
        try:
            from wotpy.protocols.coap.server import CoAPServer
            _logger.debug("Creating CoAP server on port: %s", port_coap)
            servers.append(CoAPServer(port=port_coap))
        except NotImplementedError as ex:
            _logger.warning(ex)

    if mqtt_url:
        _logger.debug("Creating MQTT server on broker: %s", mqtt_url)
        servers.append(MQTTServer(mqtt_url, servient_id=servient.hostname))

    _logger.debug("Adding servers (%s) to servient (%s)", servers, servient)
    [servient.add_server(item) for item in servers]

    return WoT(
        servient=servient,
        exposed_cb=exposed_cb,
        consumed_cb=consumed_cb)
