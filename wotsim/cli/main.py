import logging
from functools import wraps

import click
import coloredlogs

import wotsim.cli.route

_logger = logging.getLogger(__name__)


def _catch(func):
    @wraps(func)
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
@click.option("--label-net", default="org.fundacionctic.wotsim.net", show_default=True)
@click.option("--label-gateway", default="org.fundacionctic.wotsim.gw", show_default=True)
@click.option("--port-http", type=int, default=9191, show_default=True)
@click.option("--port-ws", type=int, default=9292, show_default=True)
@click.option("--port-coap", type=int, default=9393, show_default=True)
@click.option("--rtable-name", default="wotsim", show_default=True)
@click.option("--rtable-mark", type=int, default=1, show_default=True)
@click.option("--apply", type=bool, default=False, show_default=True)
@_catch
def route(**kwargs):
    wotsim.cli.route.update_routing(**kwargs)
