from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline
from django.utils.safestring import mark_safe
from django.urls import reverse
from html.parser import HTMLParser
import re


def link_render(self, tokens, idx, options, env):
    tok = tokens[idx]
    return self.renderToken(tokens, idx, options, env)


def make_link_rule(tag: str, url_fn, exists_fn):
    def _func(md):
        def link_def(state: StateInline, silent: bool) -> bool:
            pos = state.pos

            if not state.src[pos:].startswith(f"</{tag}/"):
                return False

            start = state.pos + len(f"</{tag}")
            maximum = state.posMax

            objname = None
            while True:
                pos += 1
                if pos >= maximum:
                    return False

                ch = state.srcCharCode[pos]

                if ch == 0x3C:  # /* < */
                    return False
                if ch == 0x3E:  # /* > */
                    break

            objname = state.src[start + 1 : pos]

            if not exists_fn(objname):
                return False

            target_url = url_fn(objname)

            token = state.push(f"{tag}_link_open", "a", 1)
            token.attrs = {}
            token.attrs["href"] = target_url
            token.attrs["class"] = f"{tag}-link"
            token.markup = f"{tag}_link"
            token.info = "auto"

            token = state.push("text", "", 0)
            token.content = f"/{tag}/" + objname

            token = state.push(f"{tag}_link_close", "a", -1)
            token.markup = f"{tag}_link"
            token.info = "auto"

            state.pos += len(objname) + len(f"</{tag}/>")
            return True

        md.inline.ruler.after("autolink", f"{tag}_link_def", link_def)
        md.add_render_rule(f"{tag}_link_open", link_render, fmt="html")

    return _func


# def tag_exists(name):
#    from .models import Tag
#
#    return Tag.objects.filter(name=name).exists()


def user_exists(username):
    from .models import User

    return User.objects.filter(username=username).exists()


user_link = make_link_rule(
    "u", lambda username: reverse("profile", kwargs={"username": username}), user_exists
)
# tag_link = make_link_rule("t", lambda name: f"/t/{name}", tag_exists)

MarkdownRenderer = (
    MarkdownIt("gfm-like", {"html": False}).enable(["linkify"]).use(user_link)
)


def comment_to_html(input_):
    return mark_safe(MarkdownRenderer.render(input_))


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

    @staticmethod
    def extract(input_):
        parser = Textractor()
        parser.feed(input_)
        return parser.output
