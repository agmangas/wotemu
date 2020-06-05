import logging
import os
import pprint

import coloredlogs

from clock import build_topology as clock

coloredlogs.install(level=logging.DEBUG)

_logger = logging.getLogger(__name__)


def main():
    topologies = {
        "clock": clock
    }

    _logger.info("Topologies:\n%s", pprint.pformat(topologies))

    curr_dir = os.path.dirname(os.path.realpath(__file__))

    for key, func in topologies.items():
        compose_path = os.path.join(curr_dir, "{}.yml".format(key))

        _logger.info("Building topology: %s", compose_path)

        with open(compose_path, "w") as fh:
            fh.write(func().to_compose_yaml())


if __name__ == "__main__":
    main()
