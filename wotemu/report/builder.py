import datetime
import functools
import io
import logging
import math
import os
import re
import tempfile

import lxml.etree
import numpy as np
import pandas as pd
import pkg_resources
import plotly.express as px
import plotly.graph_objects as go
import wotpy.wot.consumed.thing
import wotpy.wot.exposed.thing
from plotly.subplots import make_subplots
from wotemu.report.components.container import ContainerComponent
from wotemu.report.components.figure_block import FigureBlockComponent
from wotemu.report.components.task_list import TaskListComponent
from wotemu.report.components.task_section import TaskSectionComponent
from wotemu.report.utils import get_base_template, shorten_task_name
from wotpy.protocols.enums import InteractionVerbs

_logger = logging.getLogger(__name__)


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
        fig.update_yaxes(title_text="%", secondary_y=True)

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
                secondary_y=True)

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

    async def build_service_traffic_figure(self, inbound, colorscale="Portland", height_task=50):
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

        height = height_task * len(heatmap_y)

        fig.update_xaxes(title_text="Service")
        fig.update_yaxes(title_text="Task")
        fig.update_layout(title_text=title, height=height)

        return fig

    async def build_thing_counts_figure(self, task, facet_col_wrap=2):
        df = await self._reader.get_thing_df(task=task)

        if df.empty:
            return None

        df.reset_index(inplace=True)

        df["error_sub"] = (df["verb"] == "subscribeevent") \
            & (df["event"] == "on_error") \
            if "event" in df else False

        df["error_req"] = (df["verb"] != "subscribeevent") \
            & (df["error"].notna()) \
            if "error" in df else False

        cat_ok = "OK"
        cat_er = "Error"

        df["success"] = df["error_req"] | df["error_sub"]
        df["success"].replace(False, cat_ok, inplace=True)
        df["success"].replace(True, cat_er, inplace=True)
        df["thing"] = df["thing"] + " (" + df["class"] + ")"

        df = df.groupby(["thing", "verb", "success"]).count()

        df.reset_index(inplace=True)

        fig = px.bar(
            df,
            x="verb",
            y="host",
            color="success",
            barmode="stack",
            facet_col="thing",
            facet_col_wrap=facet_col_wrap,
            category_orders={"success": [cat_ok, cat_er]})

        fig.update_layout(title_text="Total interaction counts")
        fig.update_yaxes(title_text="Total count")
        fig.update_xaxes(title_text="Interaction verb")

        return fig

    async def _build_req_latency_fig(self, task, facet_col_wrap, cls_name):
        df = await self._reader.get_thing_df(task=task)

        if df.empty:
            return None

        df.reset_index(inplace=True)

        df = df[df["verb"].isin([
            InteractionVerbs.INVOKE_ACTION,
            InteractionVerbs.WRITE_PROPERTY,
            InteractionVerbs.READ_PROPERTY
        ])]

        df = df[df["class"] == cls_name]

        df["name_ext"] = df["name"] + " (" + df["verb"] + ")"

        if df.empty:
            return None

        fig = px.box(
            df,
            x="name_ext",
            y="latency",
            facet_col="thing",
            facet_col_wrap=facet_col_wrap)

        fig.update_yaxes(title_text="Latency (s)")
        fig.update_xaxes(title_text="Interaction name & verb")

        return fig

    async def build_consumed_request_latency_figure(self, task, facet_col_wrap=2):
        fig = await self._build_req_latency_fig(
            task=task,
            facet_col_wrap=facet_col_wrap,
            cls_name=wotpy.wot.consumed.thing.ConsumedThing.__name__)

        if not fig:
            return None

        fig.update_layout(
            title_text="Latency distribution of consumed properties and actions")

        return fig

    async def build_exposed_request_latency_figure(self, task, facet_col_wrap=2):
        fig = await self._build_req_latency_fig(
            task=task,
            facet_col_wrap=facet_col_wrap,
            cls_name=wotpy.wot.exposed.thing.ExposedThing.__name__)

        if not fig:
            return None

        fig.update_layout(
            title_text="Local handler latency distribution of exposed properties and actions")

        return fig

    async def _build_events_figure(self, task, cls_name, freq, facet_col_wrap, base_height):
        df = await self._reader.get_thing_df(task=task)

        if df.empty:
            return None

        df.reset_index(inplace=True)

        df = df[df["verb"].isin([
            InteractionVerbs.SUBSCRIBE_EVENT
        ])]

        df = df[df["class"] == cls_name]

        if df.empty:
            return None

        event_types = df["event"].unique()

        for event_type in event_types:
            df[event_type] = df["event"] == event_type
            df[event_type].replace(False, np.nan, inplace=True)

        df["name"] = df["name"] + " (" + df["thing"] + ")"

        df.set_index(["date"], inplace=True)

        df = df.groupby([
            pd.Grouper(freq=freq),
            pd.Grouper("name")
        ]).count()

        df = df.filter(event_types)
        df.reset_index(inplace=True)

        num_facets = len(df["name"].unique())

        height = math.ceil(float(num_facets) / facet_col_wrap) * base_height
        height = int(height)

        fig = px.line(
            df,
            x="date",
            y=event_types,
            facet_col="name",
            facet_col_wrap=facet_col_wrap,
            height=height)

        fig.update_yaxes(title_text="Total count")
        fig.update_xaxes(title_text="Date (UTC)")

        return fig

    async def build_consumed_events_figure(self, task, freq="10s", facet_col_wrap=2, base_height=400):
        fig = await self._build_events_figure(
            task=task,
            cls_name=wotpy.wot.consumed.thing.ConsumedThing.__name__,
            freq=freq,
            facet_col_wrap=facet_col_wrap,
            base_height=base_height)

        if not fig:
            return None

        fig.update_layout(title_text="Timeline of consumed events")

        return fig

    async def build_exposed_events_figure(self, task, freq="10s", facet_col_wrap=2, base_height=400):
        fig = await self._build_events_figure(
            task=task,
            cls_name=wotpy.wot.exposed.thing.ExposedThing.__name__,
            freq=freq,
            facet_col_wrap=facet_col_wrap,
            base_height=base_height)

        if not fig:
            return None

        fig.update_layout(title_text="Timeline of exposed events")

        return fig

    async def build_cpu_ranking_figure(self, height_task=32, height_facet=50):
        task_keys = await self._reader.get_tasks()

        if not task_keys or len(task_keys) == 0:
            return None

        info_map = await self._reader.get_info_map()

        dfs = []

        for task in task_keys:
            df = await self._reader.get_system_df(task=task)
            df.reset_index(inplace=True)
            df["task"] = shorten_task_name(task)
            df["task_short"] = shorten_task_name(task)
            task_info = info_map.get(task, {})
            df["cpu_model"] = task_info.get("cpu_model", "Unknown CPU")
            dfs.append(df)

        df_ranking = pd.concat(dfs)

        if df_ranking.empty:
            return None

        models = df_ranking["cpu_model"].unique()

        df_models = [
            df_ranking[df_ranking["cpu_model"] == model]
            for model in models
        ]

        num_tasks = len(df_ranking["task"].unique())

        row_heights = [
            float(len(df_model["task"].unique())) / num_tasks
            for df_model in df_models
        ]

        fig = make_subplots(rows=len(models), cols=1, row_heights=row_heights)

        for idx, model in enumerate(models):
            df_model = df_models[idx]

            trace = go.Box(
                x=df_model["cpu_percent"],
                y=df_model["task_short"],
                name=model)

            fig.append_trace(trace, row=(idx + 1), col=1)

        fig.update_traces(orientation="h")

        height = (len(task_keys) * height_task) + (height_facet * len(models))

        fig.update_layout(
            height=height,
            title_text="CPU distribution (by CPU model)",
            showlegend=True)

        fig.update_yaxes(title_text="Task")
        fig.update_xaxes(title_text="CPU (%)")

        return fig

    async def build_mem_ranking_figure(self, height_task=32):
        task_keys = await self._reader.get_tasks()

        if not task_keys or len(task_keys) == 0:
            return None

        dfs = []

        for task in task_keys:
            df = await self._reader.get_system_df(task=task)
            df.reset_index(inplace=True)
            df["task"] = shorten_task_name(task)
            df["task_short"] = shorten_task_name(task)
            dfs.append(df)

        df_ranking = pd.concat(dfs)

        if df_ranking.empty:
            return None

        df_sorted = df_ranking.groupby(["task"]).median()
        df_sorted.sort_values(by="mem_mb", ascending=False, inplace=True)

        height = height_task * len(task_keys)

        fig = px.box(
            df_ranking,
            category_orders={"task_short": df_sorted.index.tolist()},
            x="mem_mb",
            y="task_short",
            height=height)

        fig.update_yaxes(title_text="Task")
        fig.update_xaxes(title_text="Memory (MB)")
        fig.update_layout(title_text="Memory distribution")

        return fig

    async def build_task_timeline_figure(self, height_task=30):
        df_snap = await self._reader.get_snapshot_df()

        df_snap["finish"] = np.where(
            df_snap["is_running"] == True,
            df_snap["stopped_at"],
            df_snap["updated_at"])

        df_snap["task_short"] = df_snap["task"].apply(shorten_task_name)

        height = height_task * len(df_snap["task"].unique())

        fig = px.timeline(
            df_snap,
            x_start="created_at",
            x_end="finish",
            y="task_short",
            color="is_error",
            height=height,
            labels={"is_error": "Error"})

        fig.update_yaxes(title_text="Task")
        fig.update_xaxes(title_text="Date")
        fig.update_layout(title_text="Timeline of task containers")

        return fig

    async def _get_task_section_component(self, task):
        fig_mem = await self.build_task_mem_figure(task=task)
        fig_cpu = await self.build_task_cpu_figure(task=task)
        fig_packet_iface = await self.build_task_packet_iface_figure(task=task)
        fig_packet_proto = await self.build_task_packet_protocol_figure(task=task)
        fig_thing_counts = await self.build_thing_counts_figure(task=task)
        fig_cons_req_lat = await self.build_consumed_request_latency_figure(task=task)
        fig_exps_req_lat = await self.build_exposed_request_latency_figure(task=task)
        fig_cons_events = await self.build_consumed_events_figure(task=task)
        fig_exps_events = await self.build_exposed_events_figure(task=task)

        df_snap = await self._reader.get_snapshot_df()
        snapshot = df_snap[df_snap["task"] == task].to_dict("records")

        if len(snapshot) == 0:
            _logger.warning("Undefined snapshot data for: %s", task)

        if len(snapshot) > 1:
            _logger.warning("Multiple snapshot rows for: %s", task)

        snapshot = snapshot[-1] if len(snapshot) > 0 else None
        info = await self._reader.get_info(task, latest=True)

        return TaskSectionComponent(
            fig_mem=fig_mem,
            fig_cpu=fig_cpu,
            fig_packet_iface=fig_packet_iface,
            fig_packet_proto=fig_packet_proto,
            fig_thing_counts=fig_thing_counts,
            fig_cons_req_lat=fig_cons_req_lat,
            fig_exps_req_lat=fig_exps_req_lat,
            fig_cons_events=fig_cons_events,
            fig_exps_events=fig_exps_events,
            snapshot=snapshot,
            info=info,
            title=task)

    async def _get_service_traffic_component(self):
        fig_inbound = await self.build_service_traffic_figure(inbound=True)
        fig_outbound = await self.build_service_traffic_figure(inbound=False)

        elements = []

        if fig_inbound:
            elements.append(FigureBlockComponent(
                fig_inbound,
                title="Service traffic heatmap (inbound)",
                height=None))

        if fig_outbound:
            elements.append(FigureBlockComponent(
                fig_outbound,
                title="Service traffic heatmap (outbound)",
                height=None))

        return ContainerComponent(elements=elements)

    async def _get_system_ranking_component(self):
        fig_cpu = await self.build_cpu_ranking_figure()
        fig_mem = await self.build_mem_ranking_figure()

        elements = []

        if fig_cpu:
            elements.append(FigureBlockComponent(
                fig_cpu,
                title="CPU usage ranking",
                height=None))

        if fig_mem:
            elements.append(FigureBlockComponent(
                fig_mem,
                title="Memory usage ranking",
                height=None))

        return ContainerComponent(elements=elements)

    async def _get_header_component(self):
        title = lxml.etree.Element("h1", attrib={"class": "display-4"})
        title.text = "WoTemu report"
        sub = lxml.etree.Element("p", attrib={"class": "text-muted lead mb-0"})
        now = datetime.datetime.utcnow()
        sub.text = "Built at UTC {}".format(now.isoformat())

        return ContainerComponent(elements=[title, sub, lxml.etree.Element("hr")])

    async def _get_timeline_component(self):
        fig = await self.build_task_timeline_figure()

        elements = [FigureBlockComponent(fig, title="Tasks lifetime")] \
            if fig else []

        return ContainerComponent(elements=elements)

    async def build_report(self):
        tasks = await self._reader.get_tasks()
        tasks = sorted(tasks)

        task_pages = {}

        for task in tasks:
            task_section = await self._get_task_section_component(task=task)
            task_pages[f"{task}.html"] = task_section.to_page_html()

        df_snapshot = await self._reader.get_snapshot_df()
        task_infos = await self._reader.get_info_map()

        task_list = TaskListComponent(
            task_keys=tasks,
            task_infos=task_infos,
            df_snapshot=df_snapshot)

        service_traffic = await self._get_service_traffic_component()
        system_ranking = await self._get_system_ranking_component()
        header = await self._get_header_component()
        timeline = await self._get_timeline_component()

        container = ContainerComponent(elements=[
            header,
            service_traffic,
            system_ranking,
            timeline,
            task_list
        ])

        ret = {"index.html": container.to_page_html()}
        ret.update(task_pages)

        return ret

    async def write_report(self, base_path):
        report_pages = await self.build_report()

        for file_name, file_bytes in report_pages.items():
            file_path = os.path.join(base_path, file_name)

            with open(file_path, "wb") as fh:
                fh.write(file_bytes)
