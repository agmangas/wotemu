import xml.etree.ElementTree as ET

from wotemu.report.components.base import BaseComponent
from wotemu.report.components.figure_block import FigureBlockComponent


class ContainerComponent(BaseComponent):
    def __init__(self, elements, margin="mt-3"):
        self.elements = elements
        self.margin = margin

    def to_element(self):
        elements = []

        for item in self.elements:
            try:
                elements.append(item.to_element())
            except AttributeError:
                elements.append(item)

        container = ET.Element("div")

        for idx, el in enumerate(elements):
            row_class = f"row {self.margin}" if idx > 0 else "row"
            row = ET.Element("div", attrib={"class": row_class})
            col = ET.Element("div", attrib={"class": "col"})
            col.append(el)
            row.append(col)
            container.append(row)

        return container
