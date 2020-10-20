import tempfile
import xml.etree.ElementTree as ET

import html5lib
import pytest
from wotemu.report.builder import ReportBuilder

_TASK_SYSTEM_DF = "clock_clock.1.m8et1liyos42ljc15lkre6b71"


@pytest.mark.asyncio
async def test_build_task_mem_figure(redis_reader):
    builder = ReportBuilder(reader=redis_reader)
    fig = await builder.build_task_mem_figure(task=_TASK_SYSTEM_DF)
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
