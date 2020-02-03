import functools
import logging
import os

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

    return wrapper


@click.group()
@click.option(
    "--log-level",
    default="INFO",
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR"]),
    show_default=True)
def cli(log_level):
    root_logger_name = ".".join(__name__.split(".")[:-1])

    coloredlogs.install(
        level=log_level,
        logger=logging.getLogger(root_logger_name))


@cli.command()
@click.option("--docker-url", default="tcp://docker_api_proxy:2375/", show_default=True)
@click.option("--port-http", type=int, default=9191, show_default=True)
@click.option("--port-ws", type=int, default=9292, show_default=True)
@click.option("--port-coap", type=int, default=9393, show_default=True)
@click.option("--rtable-name", default="wotsim", show_default=True)
@click.option("--rtable-mark", type=int, default=1, show_default=True)
@click.option("--apply", is_flag=True, show_default=True)
@_catch
def route(**kwargs):
    wotsim.cli.route.update_routing(**kwargs)
