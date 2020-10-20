import io
import xml.etree.ElementTree as ET

import pandas as pd
import pkg_resources
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class ReportBuilder:
    @classmethod
    def build_figure_block_element(cls, fig, title=None, height=450, col_class="col-md", with_row=True):
        try:
            fig_io = io.StringIO()
            fig.write_html(fig_io, include_plotlyjs=False, full_html=False)
            fig_html = fig_io.getvalue()

            el_title = ET.Element("h4")

            if title:
                el_title.text = title

            el_plot = ET.fromstring(fig_html)
            el_plot.set("style", f"height: {height}px;")
            el_col = ET.Element("div", attrib={"class": col_class})
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

    async def build_report(self, plot_height=500):
        tasks = await self._reader.get_tasks()

        figs = {
            task: await self.build_task_mem_figure(task=task)
            for task in tasks
        }

        resource_path = '/'.join(("templates", "base.html"))
        template = pkg_resources.resource_string(__name__, resource_path)
        tree = ET.fromstring(template.decode())

        root = next(
            el for el in tree.find("body").iter()
            if el.attrib.get("id") == "root")

        for task, fig in figs.items():
            root.append(self.build_figure_block_element(fig, title=task))

        return ET.tostring(tree, method="html")
