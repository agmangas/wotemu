import pytest
from wotemu.report.builder import ReportBuilder

_TASK_SYSTEM_DF = "clock_clock.1.m8et1liyos42ljc15lkre6b71"


@pytest.mark.asyncio
async def test_build_task_mem(redis_reader):
    builder = ReportBuilder(reader=redis_reader)
    fig = await builder.build_task_mem(task=_TASK_SYSTEM_DF)
    assert fig
