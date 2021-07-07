from django import template
from django.utils.http import urlencode
from django.template.defaulttags import URLNode, url
from django.template.exceptions import TemplateSyntaxError
from django.template.base import Token, Node, kwarg_re

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
