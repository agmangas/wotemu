import pandas as pd
import pytest
from wotemu.report.reader import ReportDataRedisReader, explode_dict_column

_NUM_TASKS = 2
_TASK_THING_DF = "clock_clock_sub.1.3gc5vwib8jj63098et34517ed"

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
    assert len(tasks) == _NUM_TASKS


@pytest.mark.asyncio
async def test_get_system_df(redis_reader):
    tasks = await redis_reader.get_tasks()
    task = tasks.pop()
    df = await redis_reader.get_system_df(task=task)

    assert set(df.index.names) == {"date"}

    columns = [
        "cpu_percent",
        "mem_mb",
        "mem_percent"
    ]

    for col in columns:
        assert df[col].notna().any()


@pytest.mark.asyncio
async def test_get_packet_df(redis_reader):
    tasks = await redis_reader.get_tasks()
    task = tasks.pop()
    df = await redis_reader.get_packet_df(task=task)

    assert set(df.index.names) == {"date", "iface"}

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
        assert df[col].notna().any()


@pytest.mark.asyncio
async def test_get_info(redis_reader):
    tasks = await redis_reader.get_tasks()
    task = tasks.pop()
    infos = await redis_reader.get_info(task=task)

    assert len(infos) > 0

    info_item = infos[0]

    assert set(info_item.keys()) == {
        "boot_time",
        "cpu_count",
        "env",
        "mem_total",
        "net",
        "process",
        "python_version",
        "time",
        "uname"
    }


@pytest.mark.asyncio
async def test_get_thing_df(redis_reader):
    df = await redis_reader.get_thing_df(task=_TASK_THING_DF)

    assert set(df.index.names) == {"date", "thing", "name", "verb"}

    columns = [
        "event",
        "class",
        "host",
        "subscription",
        "item",
        "error"
    ]

    for col in columns:
        assert df[col].notna().any()


@pytest.mark.asyncio
async def test_explode_dict_column(redis_reader):
    df = await redis_reader.get_thing_df(task=_TASK_THING_DF)

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


@pytest.mark.asyncio
async def test_get_address_df(redis_reader):
    df = await redis_reader.get_address_df()

    assert set(df.index.names) == {"date", "iface", "task"}
    assert df["address"].notna().all()
