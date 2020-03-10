import logging

import coloredlogs

coloredlogs.install(
    level=logging.DEBUG,
    logger=logging.getLogger("wotsim"))
