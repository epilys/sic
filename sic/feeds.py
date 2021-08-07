from django.contrib.sites.shortcuts import get_current_site
from django.contrib.syndication.views import Feed
from django.http import Http404
from django.core.exceptions import PermissionDenied
from django.utils.encoding import iri_to_uri
from django.utils.feedgenerator import Atom1Feed, Rss201rev2Feed
from django.views.decorators.http import require_http_methods
from .models import Story, User
from .auth import AuthToken

# Edit site domain in /admin/sites/site/1/change


# https://github.com/django/django/blob/fbb1984046ae00bdf0b894a6b63294395da1cce8/django/contrib/syndication/views.py#L13
def add_domain(domain, url, secure=False):
    protocol = "https" if secure else "http"
    if url.startswith("//"):
        # Support network-path reference (see #16753) - RSS requires a protocol
        url = "%s:%s" % (protocol, url)
    elif not url.startswith(("http://", "https://", "mailto:")):
        url = iri_to_uri("%s://%s%s" % (protocol, domain, url))
    return url


class RssFeed(Rss201rev2Feed):
    def add_item(self, *args, **kwargs):
        if "_comments" in kwargs:
            kwargs["comments"] = kwargs["_comments"]
        return super().add_item(*args, **kwargs)


class AtomFeed(Atom1Feed):
    def add_item(self, *args, **kwargs):
        if "_comments" in kwargs:
            kwargs["comments"] = kwargs["_comments"]
        return super().add_item(*args, **kwargs)


class LatestStories(Feed):
    title = "sic latest stories"
    link = "/"
    description = ""

    def __init__(self, *args, **kwargs):
        self.request = None
        super().__init__(*args, **kwargs)

    def items(self):
        return Story.objects.order_by("-created")[:10]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.description_to_html

    def item_author_name(self, item):
        return str(item.user)

    def item_pubdate(self, item):
        return item.created

    def item_categories(self, item):
        return map(lambda t: str(t), item.tags.all())

    def item_link(self, item):
        return item.get_listing_url

    def get_context_data(self, **kwargs):
        # Bit of a hack, get_context_data() is called by the Feed view in
        # django/contrib/syndication/views.py so store the request object in
        # order to retrieve the domain from it for the comments url in
        # item_extra_kwargs()
        if "request" in kwargs:
            self.request = kwargs.get("request")
        return super().get_context_data(**kwargs)

    def item_extra_kwargs(self, item):
        link = self.item_link(item)
        url = item.get_absolute_url()
        if link != url:
            if self.request is not None:
                current_site = get_current_site(self.request)
                return {
                    "_comments": add_domain(
                        current_site.domain,
                        url,
                        self.request.is_secure(),
                    )
                }
            return {
                "_comments": url,
            }
        else:
            return {}


class LatestStoriesRss(LatestStories):
    feed_type = RssFeed
    subtitle = LatestStories.description


class LatestStoriesAtom(LatestStories):
    feed_type = AtomFeed
    subtitle = LatestStories.description


class UserLatestStoriesFeed(Feed):
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def items(self):
        return self.user.frontpage()["stories"].order_by("-created")[:10]

    def __call__(self, request, *args, **kwargs):
        if "token" in request.GET:
            token = request.GET["token"]
            if AuthToken().check_token(self.user, token):
                return super().__call__(request, *args, **kwargs)
        raise PermissionDenied("Forbidden.")


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
