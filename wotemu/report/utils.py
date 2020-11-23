import re
import xml.etree.ElementTree as ET

import pkg_resources


def get_base_template():
    resource_path = "/".join(("templates", "base.html"))
    template = pkg_resources.resource_string(__name__, resource_path)
    tree = ET.fromstring(template.decode())

    root = next(
        el for el in tree.find("body").iter()
        if el.attrib.get("id") == "root")

    return tree, root


def shorten_task_name(name):
    return re.sub(
        r"^(.+\.\d+\..{6})(.+)$",
        r"\1",
        name)
