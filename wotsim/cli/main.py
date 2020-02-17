import functools
import logging
import os
import sys

import click
import coloredlogs
import wotsim.cli.route

_logger = logging.getLogger(__name__)


def _catch(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as ex:
            _logger.error(ex)
            sys.exit(1)

    return wrapper


def _logger_cli():
    root_logger_name = ".".join(__name__.split(".")[:-1])
    return logging.getLogger(root_logger_name)


@click.group()
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    show_default=True)
@click.option("--quiet", is_flag=True, show_default=True)
def cli(log_level, quiet):
    logger = _logger_cli()

    if quiet:
        logger.propagate = False
        logger.addHandler(logging.NullHandler())
    else:
        coloredlogs.install(level=log_level, logger=logger)


@cli.command()
@click.option("--docker-url", default="tcp://docker_api_proxy:2375/", show_default=True)
@click.option("--port-http", type=int, default=os.getenv("PORT_HTTP", 80), show_default=True)
@click.option("--port-ws", type=int, default=os.getenv("PORT_WS", 81), show_default=True)
@click.option("--port-coap", type=int, default=os.getenv("PORT_COAP", 5683), show_default=True)
@click.option("--port-mqtt", type=int, default=os.getenv("PORT_MQTT", 1883), show_default=True)
@click.option("--rtable-name", default="wotsim", show_default=True)
@click.option("--rtable-mark", type=int, default=1, show_default=True)
@click.option("--apply", is_flag=True, show_default=True)
@_catch
def route(**kwargs):
    wotsim.cli.route.update_routing(**kwargs)
