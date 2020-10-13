import pytest
from wotemu.report.reader import ReportDataRedisReader


@pytest.fixture
async def redis_reader(redis_loaded):
    host, port = redis_loaded.connection.address
    redis_url = f"redis://{host}:{port}"
    reader = ReportDataRedisReader(redis_url=redis_url)
    await reader.connect()
    yield reader
    await reader.close()


@pytest.mark.asyncio
async def test_get_tasks(redis_reader):
    tasks = await redis_reader.get_tasks()
    assert len(tasks) == 2


@pytest.mark.asyncio
async def test_get_system_df(redis_reader):
    tasks = await redis_reader.get_tasks()
    task = tasks.pop()
    df = await redis_reader.get_system_df(task=task)

    columns = [
        "cpu_percent",
        "mem_mb",
        "mem_percent"
    ]

    for col in columns:
        assert len(df[col]) > 0


@pytest.mark.asyncio
async def test_get_packet_df(redis_reader):
    tasks = await redis_reader.get_tasks()
    task = tasks.pop()
    df = await redis_reader.get_packet_df(task=task)

    columns = [
        "len",
        "src",
        "dst",
        "proto",
        "transport",
        "srcport",
        "dstport"
    ]

    for col in columns:
        assert len(df[col]) > 0
