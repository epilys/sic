from django.contrib.syndication.views import Feed
from django.http import Http404, HttpResponseForbidden
from django.utils.feedgenerator import Atom1Feed
from django.views.decorators.http import require_http_methods
from .models import Story, User
from .auth import AuthToken

# Edit site domain in /admin/sites/site/1/change


class LatestStoriesRss(Feed):
    title = "sic latest stories"
    link = "/"
    description = ""

    def items(self):
        return Story.objects.order_by("-created")[:10]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.description

    def item_author_name(self, item):
        return str(item.user)

    def item_pubdate(self, item):
        return item.created

    def item_categories(self, item):
        return map(lambda t: str(t), item.tags.all())

    def item_link(self, item):
        return item.get_absolute_url()


class LatestStoriesAtom(LatestStoriesRss):
    feed_type = Atom1Feed
    subtitle = LatestStoriesRss.description


class UserLatestStoriesFeed(Feed):
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def items(self):
        return self.user.frontpage()["stories"].order_by("-created")[:10]

    def __call__(self, request, *args, **kwargs):
        if "token" in request.GET:
            token = request.GET["token"]
            if AuthToken().check_token(request.user, token):
                return super().__call__(request, *args, **kwargs)
        return HttpResponseForbidden("Forbidden.")


class UserLatestStoriesRss(UserLatestStoriesFeed, LatestStoriesRss):
    pass


class UserLatestStoriesAtom(UserLatestStoriesFeed, LatestStoriesAtom):
    pass


@require_http_methods(["GET"])
def user_feeds_rss(request, username):
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        try:
            user = User.objects.get(pk=int(username))
        except:
            raise Http404("User does not exist") from User.DoesNotExist
    return UserLatestStoriesRss(user)(request)


@require_http_methods(["GET"])
def user_feeds_atom(request, username):
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        try:
            user = User.objects.get(pk=int(username))
        except:
            raise Http404("User does not exist") from User.DoesNotExist
    return UserLatestStoriesAtom(user)(request)
