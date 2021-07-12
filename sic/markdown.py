from markdown_it import MarkdownIt
from django.utils.safestring import mark_safe
from html.parser import HTMLParser
import re


def comment_to_html(input_):
    md = MarkdownIt("gfm-like", {"html": False})
    md.enable(["linkify"])
    return mark_safe(md.render(input_))


"""Extract plain text from HTML. """


class Textractor(HTMLParser):
    whitespace = r"\s{2,}"
    output = ""
    extract_href = False

    def reset(self):
        self.output = ""
        super().reset()

    def handle_starttag(self, tag, attrs):
        attrs = {a[0]: a[1] for a in attrs}
        if tag == "a" and self.extract_href and "href" in attrs:
            self.output += re.sub(self.whitespace, " ", attrs["href"]).replace(
                "\ufeff", ""
            )
            self.output += " "

    def handle_endtag(self, tag):
        pass

    def handle_data(self, data):
        self.output += re.sub(self.whitespace, " ", data).replace("\ufeff", "")

    def extract(input_):
        parser = Textractor()
        parser.feed(input_)
        return parser.output
