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

_COMMAND_KWARGS = {
    "context_settings": {
        "show_default": True
    }
}

_logger = logging.getLogger(__name__)
_conf = wotsim.config.get_env_config()


def _catch(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as ex:
            _logger.error(ex)
            sys.exit(1)

    return wrapper


@click.group()
@click.option("--log-level", default="DEBUG")
@click.option("--quiet", is_flag=True)
def cli(log_level, quiet):
    """Root CLI command."""

    if not quiet:
        coloredlogs.install(level=log_level)


@cli.command(**_COMMAND_KWARGS)
@click.option("--docker-url", default="tcp://docker_api_proxy:2375/")
@click.option(
    "--tcp",
    type=int,
    multiple=True,
    default=[_conf.port_http, _conf.port_ws, _conf.port_mqtt, _conf.port_coap])
@click.option("--udp", type=int, multiple=True, default=[_conf.port_coap])
@click.option("--rtable-name", default="wotsim")
@click.option("--rtable-mark", type=int, default=1)
@click.option("--apply", is_flag=True)
@_catch
def route(**kwargs):
    """This command should be called in the initialization phase of all WoTsim nodes. 
    Updates the routing configuration of this container to force WoT communications to go through 
    the network gateway container. Requires access to the Docker daemon of a manager node."""

    wotsim.cli.routes.update_routing(**kwargs)


@cli.command(**_COMMAND_KWARGS)
@click.option("--docker-url", default="unix:///var/run/docker.sock")
@click.option("--netem", type=str, multiple=True)
@click.option("--duration", type=str, default="72h")
@_catch
def chaos(**kwargs):
    """This is the main command of network gateway containers. Runs and controls 
    a set of Pumba subprocesses that degrade the network stack of this container 
    to simulate real-life network conditions."""

    wotsim.cli.chaos.create_chaos(**kwargs)


@cli.command(**_COMMAND_KWARGS)
@click.option("--path", required=True, type=click.Path(exists=True))
@click.option("--func", type=str, default="app")
@click.option('--func-param', multiple=True, type=(str, str))
@click.option("--hostname", type=str, default=None)
@click.option("--enable-http", is_flag=True)
@click.option("--enable-coap", is_flag=True)
@click.option("--enable-mqtt", is_flag=True)
@click.option("--enable-ws", is_flag=True)
@_catch
def app(**kwargs):
    """Runs an user-defined WoT application injected with a decorated WoTPy entrypoint."""

    wotsim.cli.app.run_app(**kwargs)
