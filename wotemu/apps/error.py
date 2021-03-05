"""
Sleeps for a while before raising an exception.
"""

import asyncio
import logging
import random
from datetime import datetime

_logger = logging.getLogger(__name__)


async def app(wot, conf, loop, mean_time=300.0):
    mean_time = float(mean_time)
    lambd = 1.0 / mean_time
    sleep_time = random.expovariate(lambd)

    _logger.info(
        "Waiting to raise an error (mean=%s lambda=%s)",
        mean_time, lambd)

    await asyncio.sleep(sleep_time)
    now = datetime.utcnow()
    raise Exception(f"Error raised at {now} UTC")
