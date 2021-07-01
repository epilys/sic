from django.contrib.syndication.views import Feed
from django.utils.feedgenerator import Atom1Feed
from django.urls import reverse
from .models import Story


class LatestStoriesRss(Feed):
    title = "sic latest stories"
    link = "/"
    description = ""

    def items(self):
        return Story.objects.order_by("-created")[:5]

    def item_title(self, item):
        return item.title

    def item_description(self, item):
        return item.description


class LatestStoriesAtom(LatestStoriesRss):
    feed_type = Atom1Feed
    subtitle = LatestStoriesRss.description
