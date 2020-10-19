import io
import xml.etree.ElementTree as ET

import pandas as pd
import pkg_resources
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class ReportBuilder:
    def __init__(self, reader):
        self._reader = reader

    async def build_task_mem_fig(self, task):
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
            task: await self.build_task_mem_fig(task=task)
            for task in tasks
        }

        figs_html_io = {task: io.StringIO() for task in tasks}

        for task in figs_html_io.keys():
            figs[task].write_html(
                figs_html_io[task],
                include_plotlyjs=False,
                full_html=False)

        figs_html = {
            task: fig_html_io.getvalue()
            for task, fig_html_io in figs_html_io.items()
        }

        resource_path = '/'.join(("templates", "base.html"))
        template = pkg_resources.resource_string(__name__, resource_path)
        tree = ET.fromstring(template.decode())

        root = next(
            el for el in tree.find("body").iter()
            if el.attrib.get("id") == "root")

        for task, fig_html in figs_html.items():
            el_title = ET.Element("h3")
            el_title.text = task
            el_plot = ET.fromstring(fig_html)
            el_plot.set("style", f"height: {plot_height}px;")
            el_col = ET.Element("div", attrib={"class": "col-lg"})
            el_col.append(el_title)
            el_col.append(el_plot)
            el_row = ET.Element("div", attrib={"class": "row"})
            el_row.append(el_col)
            root.append(el_row)

        return ET.tostring(tree, method="html")
