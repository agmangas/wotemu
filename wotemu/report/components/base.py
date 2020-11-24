import lxml.etree
from wotemu.report.utils import get_base_template


class BaseComponent:
    def to_element(self):
        raise NotImplementedError

    def to_page_html(self):
        tree, root = get_base_template()
        root.append(self.to_element())
        return lxml.etree.tostring(tree, method="html")
