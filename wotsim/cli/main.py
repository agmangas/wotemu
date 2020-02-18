import functools
import logging
import os
import sys

import click
import coloredlogs

import wotsim.cli.chaos
import wotsim.cli.routes

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
@click.option("--log-level", default="DEBUG")
@click.option("--quiet", is_flag=True)
def cli(log_level, quiet):
    """Root CLI command."""

    logger = _logger_cli()

    if quiet:
        logger.propagate = False
        logger.addHandler(logging.NullHandler())
    else:
        coloredlogs.install(level=log_level, logger=logger)


@cli.command()
@click.option("--docker-url", default="tcp://docker_api_proxy:2375/")
@click.option("--port-http", type=int, default=os.getenv("PORT_HTTP", 80))
@click.option("--port-ws", type=int, default=os.getenv("PORT_WS", 81))
@click.option("--port-coap", type=int, default=os.getenv("PORT_COAP", 5683))
@click.option("--port-mqtt", type=int, default=os.getenv("PORT_MQTT", 1883))
@click.option("--rtable-name", default="wotsim")
@click.option("--rtable-mark", type=int, default=1)
@click.option("--apply", is_flag=True)
@_catch
def route(**kwargs):
    """This command should be called in the initialization phase of all WoTsim nodes. 
    Updates the routing configuration of this container to force WoT communications to go through 
    the network gateway container. Requires access to the Docker daemon of a manager node."""

    wotsim.cli.routes.update_routing(**kwargs)


@cli.command()
@click.option("--docker-url", default="unix:///var/run/docker.sock")
@click.option("--netem", type=str, multiple=True)
@click.option("--duration", type=str, default="72h")
@_catch
def chaos(**kwargs):
    """This is the main command of network gateway containers. Runs and controls 
    a set of Pumba subprocesses that degrade the network stack of this container 
    to simulate real-life network conditions."""

    wotsim.cli.chaos.create_chaos(**kwargs)
