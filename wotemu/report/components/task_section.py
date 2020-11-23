import xml.etree.ElementTree as ET

from wotemu.report.components.base import BaseComponent
from wotemu.report.components.figures_row import FiguresRowComponent


class TaskSectionComponent(BaseComponent):
    def __init__(self, fig_mem, fig_cpu, fig_packet_iface, fig_packet_proto, title=None, height=450):
        self.fig_mem = fig_mem
        self.fig_cpu = fig_cpu
        self.fig_packet_iface = fig_packet_iface
        self.fig_packet_proto = fig_packet_proto
        self.title = title
        self.height = height

    def to_element(self):
        figs = [
            self.fig_mem,
            self.fig_cpu,
            self.fig_packet_iface,
            self.fig_packet_proto
        ]

        figs = [item for item in figs if item is not None]

        return FiguresRowComponent(
            figs,
            col_class="col-xl-6",
            title=self.title,
            height=self.height).to_element()
