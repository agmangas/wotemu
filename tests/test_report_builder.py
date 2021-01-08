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
    report_pages = await builder.build_report()

    for file_bytes in report_pages.values():
        with tempfile.TemporaryFile() as fp:
            fp.write(file_bytes)
            fp.seek(0)
            bytes_read = fp.read()
            document = html5lib.parse(bytes_read.decode())
            assert document


@pytest.mark.asyncio
async def test_write_report(redis_reader):
    builder = ReportBuilder(reader=redis_reader)

    with tempfile.TemporaryDirectory() as tmp_dir:
        await builder.write_report(base_path=tmp_dir)


@pytest.mark.asyncio
async def test_write_report_dataset(redis_reader):
    builder = ReportBuilder(reader=redis_reader)

    with tempfile.TemporaryDirectory() as tmp_dir:
        await builder.write_report_dataset(base_path=tmp_dir)
