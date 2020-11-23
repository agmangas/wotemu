import io
import xml.etree.ElementTree as ET

from wotemu.report.components.base import BaseComponent


class FigureBlockComponent(BaseComponent):
    def __init__(self, fig, title=None, height=450, col_class="col", with_row=True):
        self.fig = fig
        self.title = title
        self.height = height
        self.col_class = col_class
        self.with_row = with_row

    def to_element(self):
        try:
            fig_io = io.StringIO()

            self.fig.write_html(
                fig_io,
                include_plotlyjs=False,
                full_html=False)

            fig_html = fig_io.getvalue()

            el_plot = ET.fromstring(fig_html)
            el_plot.set("style", f"height: {self.height}px;")
            el_col = ET.Element("div", attrib={"class": self.col_class})

            if self.title:
                el_title = ET.Element("h4")
                el_title.text = self.title
                el_col.append(el_title)

            el_col.append(el_plot)

            if not self.with_row:
                return el_col

            el_row = ET.Element("div", attrib={"class": "row"})
            el_row.append(el_col)

            return el_row
        finally:
            try:
                fig_io.close()
            except:
                pass
