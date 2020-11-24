import lxml.etree
from wotemu.report.components.base import BaseComponent
from wotemu.report.components.figure_block import FigureBlockComponent


class FiguresRowComponent(BaseComponent):
    def __init__(self, figs, title=None, height=450, col_class="col-xl"):
        self.figs = figs
        self.title = title
        self.height = height
        self.col_class = col_class

    def to_element(self):
        fig_components = [
            FigureBlockComponent(
                fig,
                title=None,
                height=self.height,
                col_class=self.col_class,
                with_row=False)
            for fig in self.figs
        ]

        el_row = lxml.etree.Element("div", attrib={"class": "row"})

        if self.title:
            el_title = lxml.etree.Element("h4")
            el_title.text = self.title

            el_title_col = lxml.etree.Element(
                "div", attrib={"class": "col-xl-12"})

            el_title_col.append(el_title)
            el_row.append(el_title_col)

        [el_row.append(item.to_element()) for item in fig_components]

        return el_row
