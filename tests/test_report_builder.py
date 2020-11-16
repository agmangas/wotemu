import tempfile
import xml.etree.ElementTree as ET

import html5lib
import pytest
from wotemu.report.builder import ReportBuilder


@pytest.mark.asyncio
async def test_build_task_mem_figure(redis_reader, redis_test_data):
    builder = ReportBuilder(reader=redis_reader)
    task = redis_test_data.get_task_with_system_data()
    fig = await builder.build_task_mem_figure(task=task)
    assert fig


@pytest.mark.asyncio
async def test_build_report(redis_reader):
    builder = ReportBuilder(reader=redis_reader)
    report_bytes = await builder.build_report()
    assert report_bytes

    with tempfile.TemporaryFile() as fp:
        fp.write(report_bytes)
        fp.seek(0)
        report_bytes_read = fp.read()
        document = html5lib.parse(report_bytes_read.decode())
        assert document
