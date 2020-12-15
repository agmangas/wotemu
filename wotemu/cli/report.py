import asyncio
import logging
from pathlib import Path

from wotemu.cli.utils import find_stack_redis_port
from wotemu.report.builder import ReportBuilder
from wotemu.report.reader import ReportDataRedisReader

_logger = logging.getLogger(__name__)


async def _connect_and_build(redis_url, base_path):
    reader = ReportDataRedisReader(redis_url=redis_url)

    try:
        await reader.connect()
        builder = ReportBuilder(reader=reader)
        Path(base_path).mkdir(parents=True, exist_ok=True)
        await builder.write_report(base_path=base_path)
    finally:
        try:
            await reader.close()
        except:
            pass


def build_report(conf, out, stack, redis_url):
    if not stack and not redis_url:
        raise ValueError("Must provide stack name when using built-in Redis")

    if not redis_url:
        redis_port = find_stack_redis_port(stack=stack)
        redis_url = f"redis://127.0.0.1:{redis_port}"

    _logger.info("Using Redis URL: %s", redis_url)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_connect_and_build(redis_url, out))
