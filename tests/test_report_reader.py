import pandas as pd
import pytest
from wotemu.report.reader import explode_dict_column


@pytest.mark.asyncio
async def test_get_tasks(redis_reader, redis_test_data):
    tasks = await redis_reader.get_tasks()
    assert len(tasks) == redis_test_data.get_num_tasks()


@pytest.mark.asyncio
async def test_get_system_df(redis_reader, redis_test_data):
    task = redis_test_data.get_task_with_system_data()
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
async def test_get_packet_df(redis_reader, redis_test_data):
    task = redis_test_data.get_task_with_packet_data()
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
        "cpu_model",
        "env",
        "mem_total",
        "net",
        "process",
        "python_version",
        "time",
        "uname",
        "service_vips",
        "hostname",
        "container_id",
        "task_id",
        "constraints",
        "networks_cidr"
    }


@pytest.mark.asyncio
async def test_get_thing_df(redis_reader, redis_test_data):
    task = redis_test_data.get_task_with_thing_data()
    df = await redis_reader.get_thing_df(task=task)

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
async def test_extend_packet_df(redis_reader, redis_test_data):
    task = redis_test_data.get_task_with_packet_data()
    df_packet = await redis_reader.get_packet_df(task=task)
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

    df_tcp = df[df["transport"] == "tcp"]
    assert df_tcp["src_service"].all()
    assert df_tcp["dst_service"].all()

    for col in columns:
        assert df[col].notna().any()


@pytest.mark.asyncio
async def test_get_service_traffic_df(redis_reader):
    df_in = await redis_reader.get_service_traffic_df(inbound=True)

    columns_in = [
        "len",
        "src_task",
        "dst_service"
    ]

    for col in columns_in:
        assert df_in[col].notna().any()

    df_out = await redis_reader.get_service_traffic_df(inbound=False)

    columns_out = [
        "len",
        "dst_task",
        "src_service"
    ]

    for col in columns_out:
        assert df_out[col].notna().any()


@pytest.mark.asyncio
async def test_get_snapshot_df(redis_reader):
    df = await redis_reader.get_snapshot_df()

    columns = [
        "desired_state",
        "is_running",
        "is_error",
        "task_id",
        "task",
        "service_id"
    ]

    for col in columns:
        assert df[col].notna().any()
