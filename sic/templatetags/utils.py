from django import template
from django.conf import settings
from django.utils.http import urlencode
from django.utils.safestring import mark_safe
from django.template.defaulttags import URLNode, url
from django.template.exceptions import TemplateSyntaxError
from django.template.base import Token, Node, kwarg_re
import subprocess, os

register = template.Library()


class URLNextNode(Node):
    def __init__(self, url_node, request):
        self.url_node = url_node
        self.request = request

    def __repr__(self):
        return "<%s url_node=%s request=%s>" % (
            self.__class__.__qualname__,
            repr(self.url_node),
            repr(self.request),
        )

    def render(self, context):
        inner = self.url_node.render(context)
        request = self.request.resolve(context)
        full_path = request.get_full_path()
        # prevent infinite loops for bots
        _next = not full_path.startswith(inner)
        _next_s = urlencode({"next": full_path})

        return inner + ("?" + _next_s) if _next else ""


@register.tag
def url_with_next(parser, token):
    bits = token.split_contents()
    if len(bits) < 3:
        raise TemplateSyntaxError(
            "'%s' takes at least two arguments, a URL pattern name and the request."
            % bits[0]
        )
    request = parser.compile_filter(bits[-1])
    bits = ["url"] + bits[1:-1]
    return URLNextNode(
        url(
            parser,
            Token(
                token.token_type,
                " ".join(bits),
                position=token.position,
                lineno=token.lineno,
            ),
        ),
        request,
    )


@register.simple_tag
def story_is_bookmarked(user, story):
    if not user.is_authenticated:
        return False
    return user.saved_stories.filter(pk=story.pk).exists()


@register.simple_tag
def comment_is_bookmarked(user, comment):
    if not user.is_authenticated:
        return False
    return user.saved_comments.filter(pk=comment.pk).exists()


@register.simple_tag
def build_sha():
    git_dir = settings.BASE_DIR
    head = subprocess.Popen(
        'git -C {dir} log -1 --pretty=format:"%h\n%s\n%cd" --date=short'.format(
            dir=git_dir
        ),
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    git_string = head.stdout.read().strip().decode("utf-8")
    [commit_sha, subject, date] = git_string.split("\n")
    return mark_safe(
        f'<span class="build"><a href="https://github.com/epilys/sic/commit/{commit_sha}"><code>[{commit_sha}]</code> {subject}</a> {date}</span>'
    )


@register.simple_tag
def user_can_view_taggregation(taggregation, request):
    return taggregation.user_has_access(request.user)


@register.simple_tag(takes_context=True)
def increment_var(context, var: str):
    context["new_" + var] = context[var] + 1
    return ""


@register.simple_tag(takes_context=True)
def get_comment_preview(context, request, comment_pk: int):
    context["preview_input"] = ""
    if isinstance(comment_pk, int):
        comment_pk = str(comment_pk)
    if (
        "comment_preview" in request.session
        and comment_pk in request.session["comment_preview"]
    ):
        context["preview_input"] = request.session["comment_preview"][comment_pk][
            "input"
        ]
        return mark_safe(request.session["comment_preview"][comment_pk]["html"])
    return None


@register.simple_tag(takes_context=True)
def comment_is_upvoted(context):
    user = context["request"].user
    if not user.is_authenticated:
        return False
    return user.votes.filter(comment=context["comment"].pk).exists()


@register.simple_tag(takes_context=True)
def story_is_upvoted(context):
    user = context["request"].user
    if not user.is_authenticated:
        return False
    return user.votes.filter(story=context["story"].pk, comment=None).exists()
