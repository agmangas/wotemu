import xml.etree.ElementTree as ET

from wotemu.report.components.base import BaseComponent
from wotemu.report.components.figure_block import FigureBlockComponent


class TaskListComponent(BaseComponent):
    DEFAULT_TITLE = "Task metrics"

    def __init__(self, task_keys, df_snapshot, title=DEFAULT_TITLE, to_href=None):
        self.task_keys = task_keys
        self.df_snapshot = df_snapshot
        self.title = title
        self.to_href = to_href if to_href else lambda x: f"{x}.html"

    def _get_item_class(self, task_key):
        df_snap = self.df_snapshot[self.df_snapshot["task"] == task_key]
        ret = "list-group-item list-group-item-action"

        if not df_snap.empty and df_snap["is_error"].any():
            ret = f"{ret} list-group-item-danger"
        elif not df_snap.empty and not df_snap["is_running"].all():
            ret = f"{ret} list-group-item-warning"
        else:
            ret = f"{ret} text-primary"

        return ret

    def _get_created_at(self, task_key):
        df_snap = self.df_snapshot[self.df_snapshot["task"] == task_key]

        if df_snap.empty:
            return None

        return df_snap.iloc[0]["created_at"]

    def _get_sorted_task_keys(self):
        return sorted(
            self.task_keys,
            key=lambda task: self._get_created_at(task))

    def to_element(self):
        task_links = []

        for task in self._get_sorted_task_keys():
            item = ET.Element("a", attrib={
                "class": self._get_item_class(task),
                "href": self.to_href(task)
            })

            task_span = ET.Element("span")
            task_span.text = task
            item.append(task_span)

            created_at = self._get_created_at(task)

            if created_at:
                dtime = ET.Element("span", attrib={"class": "ml-3 text-muted"})
                dtime.text = created_at.isoformat()
                item.append(dtime)

            task_links.append(item)

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
