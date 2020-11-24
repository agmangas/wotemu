import lxml.etree
from wotemu.report.components.base import BaseComponent
from wotemu.report.components.container import ContainerComponent
from wotemu.report.components.figure_block import FigureBlockComponent


class TaskListComponent(BaseComponent):
    DEFAULT_TITLE = "List of tasks in the emulation stack"

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
        def key(task):
            dtime = self._get_created_at(task)
            return dtime.timestamp() if dtime else 0

        return sorted(self.task_keys, key=key)

    def _get_item_element(self, task_key):
        item = lxml.etree.Element("a", attrib={
            "class": self._get_item_class(task_key),
            "href": self.to_href(task_key)
        })

        span = lxml.etree.Element("span")
        span.text = task_key
        item.append(span)

        created_at = self._get_created_at(task_key)

        if not created_at:
            return item

        dtime = lxml.etree.Element(
            "span", attrib={"class": "text-muted small"})

        dtime.text = created_at.isoformat()
        item.append(lxml.etree.Element("br"))
        item.append(dtime)

        return item

    def to_element(self):
        task_links = [
            self._get_item_element(task_key)
            for task_key in self._get_sorted_task_keys()
        ]

        title = lxml.etree.Element("h4")
        title.text = self.title

        list_group = lxml.etree.Element("div", attrib={"class": "list-group"})
        [list_group.append(item) for item in task_links]

        return ContainerComponent(elements=[title, list_group]).to_element()
