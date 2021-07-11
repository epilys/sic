from django.contrib.syndication.views import Feed
from django.utils.feedgenerator import Atom1Feed
from .models import Story

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
