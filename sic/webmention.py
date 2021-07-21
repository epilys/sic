import re, inspect, ast
import urllib.request
import urllib.parse
import logging
from html.parser import HTMLParser
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.sites.models import Site

from .apps import SicAppConfig as config
from .models import Story, Webmention


@receiver(post_save, sender=Story)
def story_created_receiver(
    sender, instance, created, raw, using, update_fields, **kwargs
):
    story = instance
    if not created or story.url is None or len(story.url) == 0 or not story.active:
        return
    if not config.SEND_WEBMENTIONS:
        print(
            "config.SEND_WEBMENTIONS = False, not sending webmention for story ",
            story.pk,
        )
    domain = Site.objects.get_current().domain
    story_url = f"https://{domain}{story.get_absolute_url()}"
    try:
        ret = post_webmention(story_url, story.url)
        if ret is not None:
            Webmention(story=story, url=ret, was_received=False).save()
    except Exception as exc:
        logger = logging.getLogger(__name__)
        logger.error(f"Could not post webmention to {story_url}:")
        logger.error(str(exc))
    return


def webmention_discovery(url):
    urlparse = urllib.parse.urlparse(url, scheme="http")
    root = f"{urlparse.scheme}://{urlparse.netloc}"

    def to_absolute(root, url):
        return urllib.parse.urljoin(root, url)

    class LinkFinder(HTMLParser):
        links = set()

        def reset(self):
            self.links = set()
            super().reset()

        def handle_starttag(self, tag, attrs):
            if tag not in ["a", "link"]:
                return
            attrs = {a[0]: a[1] for a in attrs}
            if "rel" in attrs and attrs["rel"] == "webmention":
                if "href" in attrs:
                    self.links.add(attrs["href"])

        def handle_endtag(self, tag):
            pass

        def handle_data(self, data):
            pass

        @staticmethod
        def extract(input_):
            parser = LinkFinder()
            parser.feed(input_)
            return parser.links

    def parse_header_links(value):
        """Return a dict of parsed link headers proxies.
        i.e. Link: <http:/.../front.jpeg>; rel=front; type="image/jpeg",<http://.../back.jpeg>; rel=back;type="image/jpeg"

        Implementation taken from https://github.com/kennethreitz/requests/blob/f5dacf84468ab7e0631cc61a3f1431a32e3e143c/requests/utils.py#L580
        """

        links = []

        replace_chars = " '\""

        for val in re.split(", *<", value):
            try:
                url, params = val.split(";", 1)
            except ValueError:
                url, params = val, ""

            link = {}

            link["url"] = url.strip("<> '\"")

            for param in params.split(";"):
                try:
                    key, value = param.split("=")
                except ValueError:
                    break

                link[key.strip(replace_chars)] = value.strip(replace_chars)

            links.append(link)

        return links

    links = set()

    def check_link_header(req):
        links = set()
        req.add_header("User-agent", "sic.pm Webmention discovery/urllib+python3")
        response = urllib.request.urlopen(req, timeout=3)
        link_header = response.getheader("Link")
        if link_header is not None:
            for link in parse_header_links(link_header):
                if "rel" in link and link["rel"] == "webmention":
                    links.add(link["url"])
        return (links, response)

    req = urllib.request.Request(url, method="HEAD")
    links |= check_link_header(req)[0]
    if len(links) == 0:
        req = urllib.request.Request(url, method="GET")
        (get_links, response) = check_link_header(req)
        links |= get_links
        if len(links) == 0:
            links |= LinkFinder.extract(response.read().decode("utf-8"))
    return [to_absolute(root, l) for l in links]


def post_webmention(source, target):
    links = webmention_discovery(target)
    if len(links) == 0:
        return None
    for url in links:
        req = urllib.request.Request(
            url,
            data=urllib.parse.urlencode({"source": source, "target": target}).encode(
                "utf-8"
            ),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        response = urllib.request.urlopen(req, timeout=3)
        if str(response.status).startswith("2"):
            return url
    return None
