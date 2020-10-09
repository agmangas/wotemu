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
async def test_get_nodes(redis_reader):
    nodes = await redis_reader.get_nodes()

    assert nodes == {
        "clock_clock.1.i1xmlsal6i2gh5d0dtegfwe5o",
        "clock_clock_sub.1.3gc5vwib8jj63098et34517ed"
    }


@pytest.mark.asyncio
async def test_get_system_df(redis_reader):
    nodes = await redis_reader.get_nodes()
    node = nodes.pop()
    df = await redis_reader.get_system_df(node=node)
    assert len(df["mem_mb"]) > 0


@pytest.mark.asyncio
async def test_get_packet_df(redis_reader):
    nodes = await redis_reader.get_nodes()
    node = nodes.pop()
    df = await redis_reader.get_packet_df(node=node)
    assert len(df["src"]) > 0
