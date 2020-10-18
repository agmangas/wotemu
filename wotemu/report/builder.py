import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots


class ReportBuilder:
    def __init__(self, reader):
        self._reader = reader

    async def build_task_mem(self, task):
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
