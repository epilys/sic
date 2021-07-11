from markdown_it import MarkdownIt
from django.utils.safestring import mark_safe


def comment_to_html(input_):
    md = MarkdownIt("gfm-like", {"html": False})
    md.enable(["linkify"])
    return mark_safe(md.render(input_))
