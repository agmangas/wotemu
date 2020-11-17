import functools
import io
import math
import os
import tempfile
import xml.etree.ElementTree as ET

import pandas as pd
import pkg_resources
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class ReportBuilder:
    @classmethod
    def _get_template(cls):
        resource_path = '/'.join(("templates", "base.html"))
        template = pkg_resources.resource_string(__name__, resource_path)
        tree = ET.fromstring(template.decode())

        root = next(
            el for el in tree.find("body").iter()
            if el.attrib.get("id") == "root")

        return tree, root

    @classmethod
    def build_figure_block_el(cls, fig, title=None, height=450, col_class="col", with_row=True):
        try:
            fig_io = io.StringIO()
            fig.write_html(fig_io, include_plotlyjs=False, full_html=False)
            fig_html = fig_io.getvalue()

            el_plot = ET.fromstring(fig_html)
            el_plot.set("style", f"height: {height}px;")
            el_col = ET.Element("div", attrib={"class": col_class})

            if title:
                el_title = ET.Element("h4")
                el_title.text = title
                el_col.append(el_title)

            el_col.append(el_plot)

            if not with_row:
                return el_col

            el_row = ET.Element("div", attrib={"class": "row"})
            el_row.append(el_col)

            return el_row
        finally:
            try:
                fig_io.close()
            except:
                pass

    @classmethod
    def build_figures_row_el(cls, figs, title=None, height=450, col_class="col-xl"):
        fig_elements = [
            cls.build_figure_block_el(
                fig,
                title=None,
                height=height,
                col_class=col_class,
                with_row=False)
            for fig in figs
        ]

        el_row = ET.Element("div", attrib={"class": "row"})

        if title:
            el_title = ET.Element("h4")
            el_title.text = title
            el_title_col = ET.Element("div", attrib={"class": "col-xl-12"})
            el_title_col.append(el_title)
            el_row.append(el_title_col)

        [el_row.append(item) for item in fig_elements]

        return el_row

    def __init__(self, reader):
        self._reader = reader

    async def build_task_mem_figure(self, task):
        df_system = await self._reader.get_system_df(task=task)
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

        if df is None:
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

    async def build_service_traffic_figure(self, inbound):
        df = await self._reader.get_service_traffic_df(inbound=inbound)

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
        trace = go.Heatmap(z=heatmap_z, x=heatmap_x, y=heatmap_y)
        fig.add_trace(trace)

        title = "{} traffic (KB) (service {})".format(
            "Task - service" if inbound else "Service - task",
            "inbound" if inbound else "outbound")

        fig.update_xaxes(title_text="Service")
        fig.update_yaxes(title_text="Task")
        fig.update_layout(title_text=title)

        return fig

    async def build_task_section(self, task, height=450):
        figs = [
            await self.build_task_mem_figure(task=task),
            await self.build_task_cpu_figure(task=task),
            await self.build_task_packet_iface_figure(task=task),
            await self.build_task_packet_protocol_figure(task=task)
        ]

        figs = [item for item in figs if item is not None]

        return self.build_figures_row_el(
            figs,
            col_class="col-xl-6",
            title=task,
            height=height)

    async def build_main_section(self, height=650):
        serv_traffic_rows = [
            self.build_figure_block_el(
                await self.build_service_traffic_figure(inbound=True),
                title="Service traffic heatmap (inbound)",
                height=height,
                with_row=True),
            self.build_figure_block_el(
                await self.build_service_traffic_figure(inbound=False),
                title="Service traffic heatmap (outbound)",
                height=height,
                with_row=True)
        ]

        container_row = ET.Element("div", attrib={"class": "row"})
        container_col = ET.Element("div", attrib={"class": "col"})
        container_row.append(container_col)
        [container_col.append(item) for item in serv_traffic_rows]

        return container_row

    async def build_report(self):
        tasks = await self._reader.get_tasks()
        tasks = sorted(tasks)

        task_pages = {}

        for task in tasks:
            tree, root = self._get_template()
            task_section = await self.build_task_section(task)
            root.append(task_section)
            task_pages[f"{task}.html"] = ET.tostring(tree, method="html")

        task_links = []

        for task in tasks:
            a_el = ET.Element("a", attrib={
                "class": "list-group-item list-group-item-action text-primary",
                "href": f"{task}.html"
            })

            a_el.text = task
            task_links.append(a_el)

        links_row = ET.Element("div", attrib={"class": "row"})
        links_col = ET.Element("div", attrib={"class": "col"})
        links_title = ET.Element("h4")
        links_title.text = "Task metrics"

        links_div = ET.Element("div", attrib={
            "class": "list-group list-group-flush mb-3"
        })

        links_row.append(links_col)
        links_col.append(links_title)
        links_col.append(links_div)
        [links_div.append(item) for item in task_links]

        main_section = await self.build_main_section()

        tree, root = self._get_template()
        root.append(links_row)
        root.append(main_section)

        ret = {"index.html": ET.tostring(tree, method="html")}
        ret.update(task_pages)

        return ret

    async def write_report(self, base_path):
        report_pages = await self.build_report()

        for file_name, file_bytes in report_pages.items():
            file_path = os.path.join(base_path, file_name)

            with open(file_path, "wb") as fh:
                fh.write(file_bytes)
