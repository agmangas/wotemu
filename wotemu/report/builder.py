import functools
import io
import math
import os
import re
import tempfile
import xml.etree.ElementTree as ET

import pandas as pd
import pkg_resources
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from wotemu.report.components.container import ContainerComponent
from wotemu.report.components.figure_block import FigureBlockComponent
from wotemu.report.components.task_list import TaskListComponent
from wotemu.report.components.task_section import TaskSectionComponent
from wotemu.report.utils import get_base_template, shorten_task_name


class ReportBuilder:
    def __init__(self, reader):
        self._reader = reader

    async def build_task_mem_figure(self, task):
        df_system = await self._reader.get_system_df(task=task)

        if df_system.empty:
            return None

        df_system = df_system.reset_index()

        fig = make_subplots(specs=[[{"secondary_y": True}]])

        trace_primary = go.Scatter(
            x=df_system["date"],
            y=df_system["mem_mb"],
            name="Memory (MB)")

        fig.add_trace(trace_primary, secondary_y=False)

        trace_secondary = go.Scatter(
            x=df_system["date"],
            y=df_system["mem_percent"],
            name="Memory (%)",
            line=dict(dash="dot"))

        fig.add_trace(trace_secondary, secondary_y=True)

        fig.update_layout(title_text="Memory usage")
        fig.update_xaxes(title_text="Date (UTC)")
        fig.update_yaxes(title_text="MB", secondary_y=False)
        fig.update_yaxes(title_text="%", secondary_y=True, range=[0.0, 100.0])

        return fig

    async def build_task_cpu_figure(self, task):
        df_system = await self._reader.get_system_df(task=task)

        if df_system.empty:
            return None

        df_system = df_system.reset_index()

        has_secondary = "cpu_percent_constraint" in df_system \
            and df_system["cpu_percent_constraint"].any()

        fig = make_subplots(specs=[[{"secondary_y": has_secondary}]])

        trace_primary = go.Scatter(
            x=df_system["date"],
            y=df_system["cpu_percent"],
            name="CPU total (%)")

        fig.add_trace(trace_primary, secondary_y=False)

        fig.update_layout(title_text="CPU usage")
        fig.update_xaxes(title_text="Date (UTC)")

        fig.update_yaxes(
            title_text="% over total",
            secondary_y=False)

        if has_secondary:
            trace_secondary = go.Scatter(
                x=df_system["date"],
                y=df_system["cpu_percent_constraint"],
                name="CPU constraint (%)",
                line=dict(dash="dot"))

            fig.add_trace(trace_secondary, secondary_y=True)

            fig.update_yaxes(
                title_text="% over constraint",
                secondary_y=True,
                range=[0.0, 100.0])

        return fig

    async def _build_task_packet_figure(self, task, freq, col):
        df = await self._reader.get_packet_df(task=task, extended=True)

        if df is None or df.empty:
            return None

        df = df.reset_index()
        df = df[df["dstport"].notna() & df["srcport"].notna()]

        col_series = {}
        grouper = pd.Grouper(freq=freq)

        for key in df[col].unique():
            df_key = df[df[col] == key]
            df_key.set_index(["date"], inplace=True)
            ser = df_key["len"].groupby(grouper).sum() / 1024.0
            col_series[key] = ser

        iface_traces = {
            key: go.Scatter(x=ser.index, y=ser, name=key)
            for key, ser in col_series.items()
        }

        fig = make_subplots()
        [fig.add_trace(trace) for trace in iface_traces.values()]
        fig.update_xaxes(title_text="Date (UTC)")
        fig.update_yaxes(title_text="KB")

        return fig

    async def build_task_packet_iface_figure(self, task, freq="10s"):
        fig = await self._build_task_packet_figure(
            task=task,
            freq=freq,
            col="iface")

        if not fig:
            return None

        fig.update_layout(title_text="Data transfer (by interface)")

        return fig

    async def build_task_packet_protocol_figure(self, task, freq="10s"):
        fig = await self._build_task_packet_figure(
            task=task,
            freq=freq,
            col="proto")

        if not fig:
            return None

        fig.update_layout(title_text="Data transfer (by protocol)")

        return fig

    def _get_traffic(self, df, col_service, col_task, service, task):
        df_where = df[
            (df[col_service] == service) &
            (df[col_task] == task)]

        assert len(df_where) in [0, 1]

        return 0 if df_where.empty else (df_where.iloc[0]["len"] / 1024.0)

    async def build_service_traffic_figure(self, inbound, colorscale="Portland"):
        df = await self._reader.get_service_traffic_df(inbound=inbound)

        if df.empty:
            return None

        col_service = "dst_service" if inbound else "src_service"
        col_task = "src_task" if inbound else "dst_task"

        heatmap_x = sorted(list(df[col_service].unique()))
        heatmap_y = sorted(list(df[col_task].unique()))

        get_traffic_partial = functools.partial(
            self._get_traffic,
            df=df,
            col_service=col_service,
            col_task=col_task)

        heatmap_z = [
            [
                get_traffic_partial(service=service, task=task)
                for service in heatmap_x
            ]
            for task in heatmap_y
        ]

        fig = make_subplots()

        trace = go.Heatmap(
            colorscale=colorscale,
            z=heatmap_z,
            x=[shorten_task_name(item) for item in heatmap_x],
            y=[shorten_task_name(item) for item in heatmap_y])

        fig.add_trace(trace)

        title = "{} traffic (KB) (service {})".format(
            "Task - service" if inbound else "Service - task",
            "inbound" if inbound else "outbound")

        fig.update_xaxes(title_text="Service")
        fig.update_yaxes(title_text="Task")
        fig.update_layout(title_text=title)

        return fig

    async def _get_task_section_comp(self, task):
        fig_mem = await self.build_task_mem_figure(task=task)
        fig_cpu = await self.build_task_cpu_figure(task=task)
        fig_packet_iface = await self.build_task_packet_iface_figure(task=task)
        fig_packet_proto = await self.build_task_packet_protocol_figure(task=task)

        return TaskSectionComponent(
            fig_mem=fig_mem,
            fig_cpu=fig_cpu,
            fig_packet_iface=fig_packet_iface,
            fig_packet_proto=fig_packet_proto,
            title=task)

    async def _get_service_traffic_comp(self, height=650):
        fig_inbound = await self.build_service_traffic_figure(inbound=True)
        fig_outbound = await self.build_service_traffic_figure(inbound=False)

        elements = []

        if fig_inbound:
            elements.append(FigureBlockComponent(
                fig_inbound,
                title="Service traffic heatmap (inbound)",
                height=height))

        if fig_outbound:
            elements.append(FigureBlockComponent(
                fig_outbound,
                title="Service traffic heatmap (outbound)",
                height=height))

        return ContainerComponent(elements=elements)

    async def build_report(self):
        tasks = await self._reader.get_tasks()
        tasks = sorted(tasks)

        task_pages = {}

        for task in tasks:
            task_section = await self._get_task_section_comp(task=task)
            task_pages[f"{task}.html"] = task_section.to_page_html()

        task_list = TaskListComponent(task_keys=tasks)
        service_traffic = await self._get_service_traffic_comp()
        container = ContainerComponent(elements=[task_list, service_traffic])

        ret = {"index.html": container.to_page_html()}
        ret.update(task_pages)

        return ret

    async def write_report(self, base_path):
        report_pages = await self.build_report()

        for file_name, file_bytes in report_pages.items():
            file_path = os.path.join(base_path, file_name)

            with open(file_path, "wb") as fh:
                fh.write(file_bytes)
