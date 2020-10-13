import pandas as pd
import pytest
from wotemu.report.reader import ReportDataRedisReader, explode_dict_column

pd.set_option("display.max_columns", None)


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


@pytest.mark.asyncio
async def test_get_info(redis_reader):
    tasks = await redis_reader.get_tasks()
    task = tasks.pop()
    infos = await redis_reader.get_info(task=task)

    assert len(infos) > 0
    info = infos[0]
    assert info["python_version"]
    assert info["cpu_count"]
    assert len(info["net"].keys()) > 0


async def _get_thing_df(reader):
    task = "clock_clock_sub.1.3gc5vwib8jj63098et34517ed"
    return await reader.get_thing_df(task=task)


@pytest.mark.asyncio
async def test_get_thing_df(redis_reader):
    df = await _get_thing_df(reader=redis_reader)

    columns = [
        "class",
        "host",
        "time"
    ]

    for col in columns:
        assert len(df[col]) > 0


@pytest.mark.asyncio
async def test_explode_dict_column(redis_reader):
    df = await _get_thing_df(reader=redis_reader)

    assert "item_value" not in df

    explode_dict_column(df, "item")

    assert df["item_value"].notna().any()
    assert "error_type" not in df
    assert "error_message" not in df

    explode_dict_column(df, "error")

    assert df["error_type"].notna().any()
    assert df["error_message"].notna().any()

    explode_dict_column(df, "result")

    assert "result" not in "df"
