import logging

import lxml.etree
import yaml
from wotemu.report.components.base import BaseComponent

_logger = logging.getLogger(__name__)


class CodeBlockComponent(BaseComponent):
    def __init__(self, content, title=None, subtitle=None):
        self.content = content
        self.title = title
        self.subtitle = subtitle

    def to_element(self):
        card = lxml.etree.Element("div", attrib={"class": "card"})
        card_body = lxml.etree.Element("div", attrib={"class": "card-body"})

        card_pre = lxml.etree.Element(
            "pre", attrib={"class": "mb-0 text-muted"})

        card.append(card_body)

        if self.title:
            card_title = lxml.etree.Element(
                "h5", attrib={"class": "card-title"})

            card_title.text = self.title
            card_body.append(card_title)

        if self.subtitle:
            card_subtitle = lxml.etree.Element(
                "h6", attrib={"class": "card-subtitle mb-2"})

            card_subtitle.text = self.subtitle
            card_body.append(card_subtitle)

        card_body.append(card_pre)
        card_pre.text = yaml.dump(self.content)

        return card
