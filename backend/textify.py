"""HTML as plain text: one line per paragraph, list items marked with a dash. Used for Reed's
adverts and for employers' websites."""
import re
from html.parser import HTMLParser

BLOCKS = {"p", "div", "br", "li", "ul", "ol", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}
HIDDEN = {"script", "style"}


class _Text(HTMLParser):
    def __init__(self, hidden: set):
        super().__init__(convert_charrefs=True)
        self.hide = HIDDEN | hidden
        self.parts, self.hidden = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in self.hide:
            self.hidden += 1
        elif tag in BLOCKS:
            self.parts.append("\n- " if tag == "li" else "\n")

    def handle_endtag(self, tag):
        if tag in self.hide:
            self.hidden = max(0, self.hidden - 1)
        elif tag in BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def text(html: str, hidden=()) -> str:
    """The visible text of `html`. Tags in `hidden` are left out with everything inside them."""
    parser = _Text(set(hidden))
    parser.feed(html)
    parser.close()
    lines = (re.sub(r"\s+", " ", line.replace("\xa0", " ")).strip() for line in "".join(parser.parts).split("\n"))
    return "\n".join(line for line in lines if line and line != "-")
