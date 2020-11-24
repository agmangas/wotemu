import xml.etree.ElementTree as ET

from wotemu.report.components.base import BaseComponent
from wotemu.report.components.container import ContainerComponent
from wotemu.report.components.figures_row import FiguresRowComponent


class TaskSectionComponent(BaseComponent):
    _LOGS_TITLE = "Logs"
    _LOGS_SUBTITLE = "Snapshot of the logs taken before stopping the stack"
    _NOT_RUNNING = "The task was already shutdown when the stack was stopped"
    _ERROR = "It seems there was an error during the task execution"
    _INFO_TITLE = "Task details"
    _CONTAINER_ID = "Container ID"
    _NODE_ID = "Node ID"
    _SERVICE_ID = "Service ID"
    _TASK_ID = "Task ID"
    _CREATED_AT = "Created at"
    _UPDATED_AT = "Updated at"

    def __init__(self, fig_mem, fig_cpu, fig_packet_iface, fig_packet_proto, snapshot, title=None, height=450):
        self.fig_mem = fig_mem
        self.fig_cpu = fig_cpu
        self.fig_packet_iface = fig_packet_iface
        self.fig_packet_proto = fig_packet_proto
        self.snapshot = snapshot
        self.title = title
        self.height = height

    def _get_dt(self, text):
        dt = ET.Element("dt", attrib={"class": "col-sm-3 text-muted"})
        dt.text = text
        return dt

    def _get_dd(self, text, is_code=False):
        dd = ET.Element("dd", attrib={"class": "col-sm-9 mb-0"})

        if is_code:
            code = ET.Element("code")
            code.text = text
            dd.append(code)
        else:
            dd.text = text

        return dd

    def _get_info_element(self):
        if not self.snapshot:
            return None

        card = ET.Element("div", attrib={"class": "card"})
        card_body = ET.Element("div", attrib={"class": "card-body"})
        card_title = ET.Element("h5", attrib={"class": "card-title"})
        card_title.text = self._INFO_TITLE
        card.append(card_body)
        card_body.append(card_title)

        dl = ET.Element("dl", attrib={"class": "row mb-0"})

        snap = self.snapshot

        if snap.get("node_id"):
            dl.append(self._get_dt(self._NODE_ID))
            dl.append(self._get_dd(snap["node_id"], is_code=True))

        if snap.get("service_id"):
            dl.append(self._get_dt(self._SERVICE_ID))
            dl.append(self._get_dd(snap["service_id"], is_code=True))

        if snap.get("task_id"):
            dl.append(self._get_dt(self._TASK_ID))
            dl.append(self._get_dd(snap["task_id"], is_code=True))

        if snap.get("container_id"):
            dl.append(self._get_dt(self._CONTAINER_ID))
            dl.append(self._get_dd(snap["container_id"], is_code=True))

        if snap.get("created_at"):
            dl.append(self._get_dt(self._CREATED_AT))
            dl.append(self._get_dd(snap["created_at"].isoformat()))

        if snap.get("updated_at"):
            dl.append(self._get_dt(self._UPDATED_AT))
            dl.append(self._get_dd(snap["updated_at"].isoformat()))

        card_body.append(dl)

        return card

    def _get_logs_element(self):
        if not self.snapshot:
            return None

        card = ET.Element("div", attrib={"class": "card"})
        is_error = self.snapshot.get("is_error", False)
        body_class = "bg-warning" if is_error else "bg-light"
        body_class = f"card-body small {body_class}"
        card_body = ET.Element("div", attrib={"class": body_class})
        card_pre = ET.Element("pre", attrib={"class": "mb-0"})
        card_title = ET.Element("h5", attrib={"class": "card-title"})
        card_title.text = self._LOGS_TITLE

        card_subtitle = ET.Element(
            "h6", attrib={"class": "card-subtitle mb-2 text-muted"})

        card_subtitle.text = self._LOGS_SUBTITLE
        card.append(card_body)
        card_body.append(card_title)
        card_body.append(card_subtitle)
        card_body.append(card_pre)
        card_pre.text = self.snapshot["logs"].strip()

        return card

    def _get_running_element(self):
        if not self.snapshot:
            return None

        if self.snapshot.get("is_running", True):
            return None

        alert = ET.Element("div", attrib={"class": f"alert alert-warning"})
        alert.text = self._NOT_RUNNING

        return alert

    def _get_error_element(self):
        if not self.snapshot:
            return None

        if not self.snapshot.get("is_error", False):
            return None

        alert = ET.Element("div", attrib={"class": f"alert alert-danger"})
        alert.text = self._ERROR

        return alert

    def to_element(self):
        figs = [
            self.fig_mem,
            self.fig_cpu,
            self.fig_packet_iface,
            self.fig_packet_proto
        ]

        figs = [item for item in figs if item is not None]

        figs_row = FiguresRowComponent(
            figs,
            col_class="col-xl-6",
            height=self.height).to_element()

        title = None

        if self.title:
            title = ET.Element("h4")
            title.text = self.title

        elements = [
            title,
            self._get_running_element(),
            self._get_error_element(),
            self._get_info_element(),
            figs_row,
            self._get_logs_element()
        ]

        elements = [item for item in elements if item is not None]

        return ContainerComponent(elements=elements).to_element()
