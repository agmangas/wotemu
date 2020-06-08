import importlib
import logging
import os
import sys

from wotemu.utils import import_func

_logger = logging.getLogger(__name__)


def _default_output_path(path):
    path_root, path_base = os.path.split(path)
    name, _ext = os.path.splitext(path_base)
    return os.path.join(path_root, "{}.yml".format(name))


def build_compose(conf, path, output, func):
    topology_func = import_func(path, func)
    _logger.info("Imported topology function: %s", topology_func)
    output = output if output else _default_output_path(path)
    _logger.info("Writing Compose file to: %s", output)
    compose_yaml = topology_func().to_compose_yaml()

    with open(output, "w") as fh:
        fh.write(compose_yaml)
