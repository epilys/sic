import re
import urllib.request
import urllib.parse
import ipaddress
from html.parser import HTMLParser
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import resolve
from django.contrib.sites.models import Site
from django.conf import settings
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
)
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.apps import apps

config = apps.get_app_config("sic")
from sic.models import Story
from sic.views.utils import check_safe_url


class Webmention(models.Model):
    id = models.AutoField(primary_key=True)
    story = models.ForeignKey(
        Story, related_name="webmentions", on_delete=models.CASCADE
    )
    url = models.URLField(null=False, blank=False)
    source = models.URLField(null=False, blank=False)
    target = models.URLField(null=False, blank=False)
    created = models.DateTimeField(auto_now_add=True)
    was_received = models.BooleanField(
        default=True, null=False
    )  # did we sent it or did we receive it?

    class Meta:
        ordering = ["-created", "story"]

    def __str__(self):
        return f"{self.id} {self.story} {self.url}"


class LinkFinder(HTMLParser):
    links = set()
    webmention_links = set()

    def reset(self):
        self.links = set()
        self.webmention_links = set()
        super().reset()

    def handle_starttag(self, tag, attrs):
        if tag not in ["a", "link"]:
            return
        attrs = {a[0]: a[1] for a in attrs}
        if "rel" in attrs and any(v == "webmention" for v in attrs["rel"].split()):
            if "href" in attrs:
                self.webmention_links.add(attrs["href"])
        elif "href" in attrs:
            self.links.add(attrs["href"])

    def handle_endtag(self, tag):
        pass

    def handle_data(self, data):
        pass

    @staticmethod
    def extract(input_):
        linkparser = LinkFinder()
        linkparser.feed(input_)
        return {
            "links": linkparser.links,
            "webmention_links": linkparser.webmention_links,
        }


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
        return
    domain = Site.objects.get_current().domain
    story_url = (
        f"http://{domain}{story.get_absolute_url()}"
        if settings.DEBUG
        else f"https://{domain}{story.get_absolute_url()}"
    )
    from sic.jobs import Job, JobKind

    # schedule job
    kind = JobKind.from_func(webmention_send)
    _job_obj, _ = Job.objects.get_or_create(
        kind=kind,
        periodic=False,
        data={"source": story_url, "target": story.url, "story_pk": story.pk},
    )
    return


def webmention_discovery(url):
    """Checks url for webmention endpoints.
    - First tries a HEAD request and looks at the HTTP response headers.
    - Then does a GET request and looks for webmention links in the body.
    """

    def to_absolute(root, url):
        return urllib.parse.urljoin(root, url)

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

    def check_link_header(req):
        links = set()
        req.add_header("User-agent", "Webmention discovery/urllib+python3")
        with urllib.request.urlopen(req, timeout=3) as response:
            link_header = response.getheader("Link")
            if link_header is not None:
                for link in parse_header_links(link_header):
                    if "rel" in link and any(
                        v == "webmention" for v in link["rel"].split()
                    ):
                        links.add(link["url"])
            body = response.read().decode("utf-8")
        return (links, body)

    urlparse = urllib.parse.urlparse(url, scheme="http")
    root = f"{urlparse.scheme}://{urlparse.netloc}"
    links = set()
    req = urllib.request.Request(url, method="HEAD")
    links |= check_link_header(req)[0]
    if len(links) == 0:
        req = urllib.request.Request(url, method="GET")
        (get_links, response) = check_link_header(req)
        links |= get_links
        if len(links) == 0:
            links |= LinkFinder.extract(response)["webmention_links"]
    return [to_absolute(root, l) for l in links]


def webmention_post(source, target):
    links = webmention_discovery(target)
    if len(links) == 0:
        return None
    for url in links:
        if not settings.DEBUG:
            if not check_safe_url(url):
                raise ValueError(
                    f"Webmention endpoint is invalid: {url}. Malicious or misconfigured endpoint."
                )
        req = urllib.request.Request(
            url,
            data=urllib.parse.urlencode({"source": source, "target": target}).encode(
                "utf-8"
            ),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=3) as response:
            if str(response.status).startswith("2"):
                return url
    return None


def webmention_send(job):
    source = job.data["source"]
    target = job.data["target"]
    story_pk = job.data["story_pk"]
    ret = webmention_post(source, target)
    if ret is not None:
        Webmention(
            story_pk=story_pk, url=ret, source=source, target=target, was_received=False
        ).save()
        return f"Sent webmention to {ret}"
    return f"No webmention endpoint found at {target}"


def webmention_receive(job):
    source = job.data["source"]
    target = job.data["target"]
    if source == target:
        raise ValueError("Received Webmention has source == target:", source)
    if not check_safe_url(source):
        raise ValueError("Received Webmention source is invalid:", source)
    sourceparsed = urllib.parse.urlparse(source)
    targetparsed = urllib.parse.urlparse(target)
    netloc = targetparsed.netloc.split(sep=":", maxsplit=1)[0]
    if not settings.DEBUG and netloc != Site.objects.get_current().domain:
        raise ValueError(
            "Received Webmention target is not our domain: source=",
            source,
            "target=",
            target,
        )
    match = resolve(targetparsed[2])
    story_pk = None
    if match.view_name == "story":
        story_pk = match.kwargs["story_pk"]
    with urllib.request.urlopen(
        urllib.request.Request(
            source,
            method="GET",
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.163 Safari/537.36",
            },
        ),
        timeout=3,
    ) as response:
        if not "text/html" in response.getheader("Content-Type"):
            return f"""Content-Type is {response.getheader("Content-Type")}"""
        links = LinkFinder.extract(response.read().decode("utf-8"))["links"]
        if target not in links:
            return f"target {target} was not found in source {source} document. Found these links: {links}"
        Webmention(
            story_id=story_pk,
            url=targetparsed[2],
            source=source,
            target=target,
            was_received=True,
        )
        return f"Received webmention for target {target} from source {source}."


@csrf_exempt
@require_http_methods(["POST"])
def webmention_endpoint(request):
    if "source" not in request.POST or "target" not in request.POST:
        return HttpResponseBadRequest()
    source = request.POST["source"]
    target = request.POST["target"]
    try:
        if source == target:
            raise ValueError("Received Webmention has source == target:", source)
        sourceparsed = urllib.parse.urlparse(source)
        targetparsed = urllib.parse.urlparse(target)
        netloc = targetparsed.netloc.split(sep=":", maxsplit=1)[0]
        if not settings.DEBUG and netloc != Site.objects.get_current().domain:
            raise ValueError

        # raises Http404 if target does not resolve
        _match = resolve(targetparsed[2])

        from sic.jobs import Job, JobKind

        # schedule job
        kind = JobKind.from_func(webmention_receive)
        _job_obj, _ = Job.objects.get_or_create(
            kind=kind, periodic=False, data={"source": source, "target": target}
        )
        return HttpResponse(status=202)
    except (ValueError, Http404):
        return HttpResponseBadRequest()
