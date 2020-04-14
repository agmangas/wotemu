import functools
import logging
import os
import sys

import click
import coloredlogs

import wotsim.cli.app
import wotsim.cli.chaos
import wotsim.cli.routes
import wotsim.config

_logger = logging.getLogger(__name__)
_env_config = wotsim.config.get_env_config()


def _catch(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as ex:
            _logger.error(ex)
            sys.exit(1)

    return wrapper


def _logger_root():
    root_logger_name = __name__.split(".")[0]
    return logging.getLogger(root_logger_name)


@click.group()
@click.option("--log-level", default="DEBUG")
@click.option("--quiet", is_flag=True)
def cli(log_level, quiet):
    """Root CLI command."""

    if not quiet:
        coloredlogs.install(level=log_level, logger=_logger_root())


@cli.command()
@click.option("--docker-url", default="tcp://docker_api_proxy:2375/")
@click.option("--port-http", type=int, default=_env_config.port_http)
@click.option("--port-ws", type=int, default=_env_config.port_ws)
@click.option("--port-coap", type=int, default=_env_config.port_coap)
@click.option("--port-mqtt", type=int, default=_env_config.port_mqtt)
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


@cli.command()
@click.option("--path", required=True, type=click.Path(exists=True))
@click.option("--func", type=str, default="app")
@click.option("--port-catalogue", type=int, default=_env_config.port_catalogue)
@click.option("--port-http", type=int, default=_env_config.port_http)
@click.option("--port-ws", type=int, default=_env_config.port_ws)
@click.option("--port-coap", type=int, default=_env_config.port_coap)
@click.option("--mqtt-url", type=str, default=_env_config.mqtt_url)
@click.option("--redis-url", type=str, default=_env_config.redis_url)
@_catch
def app(**kwargs):
    """Runs an user-defined WoT application injected with a decorated WoTPy entrypoint."""

    wotsim.cli.app.run_app(**kwargs)
