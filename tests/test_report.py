import pandas as pd
import pytest
from wotemu.report.reader import ReportDataRedisReader, explode_dict_column

_NUM_TASKS = 4
_TASK_SYSTEM_DF = "clock_clock.1.m7q9itb8mh7677kl1msu45zek"
_TASK_THING_DF = "clock_clock.1.m7q9itb8mh7677kl1msu45zek"
_TASK_PACKET_DF = "clock_clock.1.m7q9itb8mh7677kl1msu45zek"

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
    df = await redis_reader.get_system_df(task=_TASK_SYSTEM_DF)

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
    df = await redis_reader.get_packet_df(task=_TASK_PACKET_DF)

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
        "class",
        "host"
    ]

    for col in columns:
        assert df[col].notna().any()


@pytest.mark.asyncio
async def test_explode_dict_column():
    df = pd.DataFrame([
        {"key": "A0", "error": {"type": "ValueError", "message": "An error"}},
        {"key": "A1", "item": 10},
        {"key": "A2", "item": {"value": 20}}
    ])

    explode_dict_column(df, "item")

    assert df["item"].notna().any()
    assert df["item_value"].notna().any()

    explode_dict_column(df, "error")

    assert df["error"].notna().any()
    assert df["error_type"].notna().any()
    assert df["error_message"].notna().any()


@pytest.mark.asyncio
async def test_get_address_df(redis_reader):
    df = await redis_reader.get_address_df()

    assert set(df.index.names) == {"date", "iface", "task"}
    assert df["address"].notna().all()


@pytest.mark.asyncio
async def test_extend_packet_df(redis_reader):
    df_packet = await redis_reader.get_packet_df(task=_TASK_PACKET_DF)
    df = await redis_reader.extend_packet_df(df_packet)

    assert set(df.index.names) == {"date", "iface"}

    columns = [
        "len",
        "src",
        "dst",
        "proto",
        "transport",
        "srcport",
        "dstport",
        "src_task",
        "src_service",
        "dst_task",
        "dst_service"
    ]

    for col in columns:
        assert df[col].notna().any()
