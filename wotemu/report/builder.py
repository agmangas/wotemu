import io
import math
import xml.etree.ElementTree as ET

import pandas as pd
import pkg_resources
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class ReportBuilder:
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

    async def build_task_packet_figure(self, task, freq="10s"):
        df = await self._reader.get_packet_df(task=task, extended=True)

        if df is None:
            return None

        df = df.reset_index()
        df = df[df["dstport"].notna() & df["srcport"].notna()]

        iface_series = {}
        grouper = pd.Grouper(freq=freq)

        for iface in df["iface"].unique():
            df_iface = df[df["iface"] == iface]
            df_iface.set_index(["date"], inplace=True)
            iface_series[iface] = df_iface["len"].groupby(grouper).sum()
            iface_series[iface] /= 1024.0

        iface_traces = {
            iface: go.Scatter(x=ser.index, y=ser, name=iface)
            for iface, ser in iface_series.items()
        }

        fig = make_subplots()
        [fig.add_trace(trace) for trace in iface_traces.values()]
        fig.update_layout(title_text="Data transfer")
        fig.update_xaxes(title_text="Date (UTC)")
        fig.update_yaxes(title_text="KB")

        return fig

    async def build_report(self, plot_height=500):
        tasks = await self._reader.get_tasks()

        figs_mem = {
            task: await self.build_task_mem_figure(task=task)
            for task in tasks
        }

        figs_cpu = {
            task: await self.build_task_cpu_figure(task=task)
            for task in tasks
        }

        figs_packet = {
            task: await self.build_task_packet_figure(task=task)
            for task in tasks
        }

        resource_path = '/'.join(("templates", "base.html"))
        template = pkg_resources.resource_string(__name__, resource_path)
        tree = ET.fromstring(template.decode())

        root = next(
            el for el in tree.find("body").iter()
            if el.attrib.get("id") == "root")

        for task in sorted(figs_mem.keys()):
            task_figs = [figs_mem[task], figs_cpu[task]]

            if figs_packet.get(task):
                task_figs.append(figs_packet[task])

            task_row = self.build_figures_row_el(
                task_figs,
                col_class="col-xl-6",
                title=task)

            root.append(task_row)

        return ET.tostring(tree, method="html")
