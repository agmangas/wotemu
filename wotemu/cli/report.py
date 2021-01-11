import asyncio
import logging
from datetime import datetime
from pathlib import Path

from wotemu.cli.utils import find_stack_redis_port
from wotemu.report.builder import ReportBuilder
from wotemu.report.reader import ReportDataRedisReader

_logger = logging.getLogger(__name__)


async def _connect_and_build(redis_url, base_path, as_json, file_name):
    reader = ReportDataRedisReader(redis_url=redis_url)

    try:
        await reader.connect()
        builder = ReportBuilder(reader=reader)
        Path(base_path).mkdir(parents=True, exist_ok=True)

        if as_json:
            _logger.info("Writing report as raw JSON")

            await builder.write_report_dataset(
                base_path=base_path,
                file_name=file_name)
        else:
            _logger.info("Writing report as HTML page")
            await builder.write_report(base_path=base_path)
    finally:
        try:
            await reader.close()
        except:
            pass


def build_report(conf, out, stack, redis_url, as_json):
    if not stack and not redis_url:
        raise ValueError((
            "You must provide either an explicit Redis URL "
            "or the name of the stack. This command must "
            "be executed in a manager node if you choose "
            "to provide the name of the stack."
        ))

    if not redis_url:
        redis_port = find_stack_redis_port(stack=stack)
        redis_url = f"redis://127.0.0.1:{redis_port}"

    _logger.info("Using Redis URL: %s", redis_url)

    dtime = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    file_name = f"wotemu_{dtime}"
    file_name = f"{file_name}_{stack}" if stack else file_name

    loop = asyncio.get_event_loop()

    loop.run_until_complete(_connect_and_build(
        redis_url=redis_url,
        base_path=out,
        as_json=as_json,
        file_name=file_name))
