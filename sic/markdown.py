from html.parser import HTMLParser
import re
from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline
from django.utils.safestring import mark_safe
from django.urls import reverse, resolve


def link_render(self, tokens, idx, options, env):
    return self.renderToken(tokens, idx, options, env)


def make_link_rule(tag: str, url_fn, exists_fn, detect_fn=None):
    if detect_fn is None:
        detect_fn = lambda t: len(f"</{tag}") if t.startswith(f"</{tag}/") else False

    def _func(markdown):
        def link_def(state: StateInline, _silent: bool) -> bool:
            pos = state.pos

            detect = detect_fn(state.src[pos:])
            if not detect:
                return False
            start = state.pos + detect

            maximum = state.posMax

            objname = None
            while True:
                pos += 1
                if pos >= maximum:
                    return False

                char = state.srcCharCode[pos]

                if char == 0x3C:  # /* < */
                    return False
                if char == 0x3E:  # /* > */
                    break

            objname = state.src[start + 1 : pos]
            exists = exists_fn(objname)

            if not exists:
                return False

            target_url = url_fn(objname)

            token = state.push(f"{tag}_link_open", "a", 1)
            token.attrs = {}
            token.attrs["href"] = target_url
            token.attrs["class"] = f"{tag}-link"
            token.markup = f"{tag}_link"
            token.info = "auto"

            token = state.push("text", "", 0)
            if isinstance(exists, str):
                token.content = exists
            else:
                token.content = f"/{tag}/" + objname

            token = state.push(f"{tag}_link_close", "a", -1)
            token.markup = f"{tag}_link"
            token.info = "auto"

            state.pos = pos + len(">")
            return True

        markdown.inline.ruler.after("autolink", f"{tag}_link_def", link_def)
        markdown.add_render_rule(f"{tag}_link_open", link_render, fmt="html")

    return _func


def user_exists(username):
    from .models import User

    return User.objects.filter(username=username).exists()


user_link = make_link_rule(
    "u", lambda username: reverse("profile", kwargs={"name": username}), user_exists
)


def tag_exists(name):
    from .models import Tag

    tag = Tag.objects.filter(name=name)
    if not tag.exists():
        return False
    return tag.first().name


def tag_url(name):
    from .models import Tag

    return Tag.objects.filter(name=name).first().get_absolute_url()


tag_link = make_link_rule("t", tag_url, tag_exists)


def story_exists(story_url):
    from .models import Story
    from .views import stories

    try:
        func, args, kwargs = resolve(f"/{story_url}")
        if func == stories.story:
            story_obj = Story.objects.get(pk=kwargs["story_pk"])
            return story_obj.title
        return False
    except Exception:
        return False


story_link = make_link_rule(
    "story_tag",
    lambda story_url: f"/{story_url}",
    story_exists,
    detect_fn=lambda t: 1 if t.startswith("</") else False,
)
# tag_link = make_link_rule("t", lambda name: f"/t/{name}", tag_exists)

MarkdownRenderer = (
    MarkdownIt("gfm-like", {"html": False})
    .enable(["linkify"])
    .use(user_link)
    .use(tag_link)
    .use(story_link)
)


def comment_to_html(input_):
    return mark_safe(MarkdownRenderer.render(input_))


# Extract plain text from HTML.


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
