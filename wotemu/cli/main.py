import functools
import logging
import os
import sys

import click
import coloredlogs
import wotemu.cli.app
import wotemu.cli.broker
import wotemu.cli.chaos
import wotemu.cli.compose
import wotemu.cli.limits
import wotemu.cli.report
import wotemu.cli.routes
import wotemu.cli.stop
import wotemu.cli.waiter
import wotemu.config

_COMMAND_KWARGS = {
    "context_settings": {
        "show_default": True
    }
}

_DEFAULT_DOCKER_SOCK = "unix://{}".format(wotemu.config.DEFAULT_DOCKER_SOCKET)

_logger = logging.getLogger(__name__)


def _catch(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            _logger.error("CLI error", exc_info=True)
            sys.exit(1)

    return wrapper


@click.group()
@click.option("--log-level", default="DEBUG")
@click.option("--quiet", is_flag=True)
@click.option("--root-logger", is_flag=True)
@click.pass_context
def cli(ctx, log_level, quiet, root_logger):
    """Root CLI command."""

    logging.getLogger().addHandler(logging.NullHandler())

    if not quiet:
        pkg_name = __name__.split(".")[0]
        cli_logger_name = None if root_logger else pkg_name
        cli_logger = logging.getLogger(cli_logger_name)
        coloredlogs.install(level=log_level, logger=cli_logger)

    wotemu.config.log_config()
    ctx.obj = wotemu.config.get_env_config()


@cli.command(**_COMMAND_KWARGS)
@click.option("--rtable-name", default="wotemu")
@click.option("--rtable-mark", type=int, default=1)
@click.option("--apply", is_flag=True)
@click.pass_obj
@_catch
def route(conf, **kwargs):
    """This command should be called in the initialization phase of all WoTemu nodes. 
    Updates the routing configuration of this container to force WoT communications to go through 
    the network gateway container. Requires access to the Docker daemon of a manager node."""

    wotemu.cli.routes.update_routing(conf, **kwargs)


@cli.command(**_COMMAND_KWARGS)
@click.option("--docker-url", default=_DEFAULT_DOCKER_SOCK)
@click.option("--netem", type=str, multiple=True)
@click.option("--duration", type=str, default="72h")
@click.pass_obj
@_catch
def chaos(conf, **kwargs):
    """This is the main command of network gateway containers. Runs and controls 
    a set of Pumba subprocesses that degrade the network stack of this container 
    to simulate real-life network conditions."""

    wotemu.cli.chaos.create_chaos(conf, **kwargs)


@cli.command(**_COMMAND_KWARGS)
@click.option("--path", required=True, type=str)
@click.option("--func", type=str, default="app")
@click.option('--func-param', multiple=True, type=(str, str))
@click.option("--hostname", type=str, default=None)
@click.option("--enable-http", is_flag=True)
@click.option("--enable-coap", is_flag=True)
@click.option("--enable-mqtt", is_flag=True)
@click.option("--enable-ws", is_flag=True)
@click.option("--disable-monitor", is_flag=True)
@click.pass_obj
@_catch
def app(conf, **kwargs):
    """Runs a user-defined WoT application injected with a decorated WoTPy entrypoint."""

    wotemu.cli.app.run_app(conf, **kwargs)


@cli.command(**_COMMAND_KWARGS)
@click.option("--path", required=True, type=str)
@click.option("--output", type=str, default=None)
@click.option("--func", type=str, default="topology")
@click.pass_obj
@_catch
def compose(conf, **kwargs):
    """Takes a topology definition and builds a Compose file for emulation."""

    wotemu.cli.compose.build_compose(conf, **kwargs)


@cli.command(**_COMMAND_KWARGS)
@click.option("--docker-url", default=_DEFAULT_DOCKER_SOCK)
@click.option("--speed", type=int, required=True)
@click.option("--timeout", type=int, default=300)
@click.option("--wait", type=int, default=2)
@click.option("--local", is_flag=True)
@click.pass_obj
@_catch
def limits(conf, **kwargs):
    """Updates the CPU performance limits from inside a WoTemu container."""

    wotemu.cli.limits.update_limits(conf, **kwargs)


@cli.command(**_COMMAND_KWARGS)
@click.option("--sleep", type=float, default=1.0)
@click.option("--timeout", type=float, default=60.0)
@click.option("--waiter-base", is_flag=True)
@click.option("--waiter-mqtt", is_flag=True)
@click.pass_obj
@_catch
def wait(conf, **kwargs):
    """Waits for the services of the WoTemu stack to be available."""

    wotemu.cli.waiter.wait_services(conf, **kwargs)


@cli.command(**_COMMAND_KWARGS)
@click.option("--disable-monitor", is_flag=True)
@click.pass_obj
@_catch
def broker(conf, **kwargs):
    """Runs a MQTT broker."""

    wotemu.cli.broker.run_mqtt_broker(conf, **kwargs)


@cli.command(**_COMMAND_KWARGS)
@click.option("--compose-file", required=True)
@click.option("--stack", required=True)
@click.option("--redis-url", default=None)
@click.option("--tail", type=int, default=60)
@click.pass_obj
@_catch
def stop(conf, **kwargs):
    """Stops an emulation stack that is currently active. 
    Unlike 'docker stack rm' this keeps the in-memory traces 
    if necessary and logs other events of interest."""

    wotemu.cli.stop.stop_stack(conf, **kwargs)


@cli.command(**_COMMAND_KWARGS)
@click.option("--out", required=True)
@click.option("--stack", default=None)
@click.option("--redis-url", default=None)
@click.option("--json", is_flag=True)
@click.pass_obj
@_catch
def report(conf, **kwargs):
    """Builds an emulation stack report."""

    kwargs["as_json"] = kwargs.pop("json", False)
    wotemu.cli.report.build_report(conf, **kwargs)
