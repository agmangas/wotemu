import xml.etree.ElementTree as ET

from wotemu.report.components.base import BaseComponent
from wotemu.report.components.figure_block import FigureBlockComponent


class TaskListComponent(BaseComponent):
    DEFAULT_TITLE = "Task metrics"

    def __init__(self, task_keys, title=DEFAULT_TITLE, to_href=None):
        self.task_keys = task_keys
        self.title = title
        self.to_href = to_href if to_href else lambda x: f"{x}.html"

    def to_element(self):
        task_links = []

        for task in self.task_keys:
            a_el = ET.Element("a", attrib={
                "class": "list-group-item list-group-item-action text-primary",
                "href": self.to_href(task)
            })

            a_el.text = task
            task_links.append(a_el)

        row = ET.Element("div", attrib={"class": "row"})
        col = ET.Element("div", attrib={"class": "col"})
        title = ET.Element("h4")
        title.text = self.title
        list_group = ET.Element("div", attrib={"class": "list-group"})
        row.append(col)
        col.append(title)
        col.append(list_group)
        [list_group.append(item) for item in task_links]

        return row
