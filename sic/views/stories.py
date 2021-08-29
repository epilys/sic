from html.parser import HTMLParser
from datetime import datetime
import hashlib
import urllib.request
from django.db import transaction
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from django.views.decorators.http import require_safe
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse
from django.apps import apps

config = apps.get_app_config("sic")
from sic.models import Story, StoryKind, Comment, Notification, StoryRemoteContent, Tag
from sic.forms import (
    SubmitCommentForm,
    SubmitStoryForm,
    EditStoryForm,
    OrderByForm,
)
from sic.markdown import comment_to_html
from sic.views.utils import (
    form_errors_as_string,
    Paginator,
    InvalidPage,
    check_safe_url,
    check_next_url,
)
from sic.moderation import ModerationLogEntry


def story(request, story_pk, slug=None):
    try:
        story_obj = Story.objects.get(pk=story_pk)
    except Story.DoesNotExist:
        raise Http404("Story does not exist") from Story.DoesNotExist
    ongoing_reply_pk = None
    try:
        comment_pk = next(iter(request.session["comment_preview"].keys()))
        comment_pk = comment_pk if comment_pk == "null" else int(comment_pk)
        ongoing_reply_pk = comment_pk
    except (StopIteration, KeyError, ValueError):
        pass
    if request.method == "POST":
        form = SubmitCommentForm(request.POST)
        if not request.user.is_authenticated:
            messages.add_message(
                request, messages.ERROR, "You must be logged in to comment."
            )
        elif not request.user.has_perm("sic.add_comment"):
            if request.user.banned_by_user is not None:
                messages.add_message(
                    request,
                    messages.ERROR,
                    "You are banned and not allowed to comment.",
                )
            else:
                messages.add_message(
                    request, messages.ERROR, "You are not allowed to comment."
                )
        else:
            if form.is_valid():
                comment = Comment.objects.create(
                    user=request.user,
                    story=story_obj,
                    parent=None,
                    text=form.cleaned_data["text"],
                )
                request.session["comment_preview"] = {}
                return redirect(comment)
            error = form_errors_as_string(form.errors)
            messages.add_message(
                request, messages.ERROR, f"Invalid comment form. Error: {error}"
            )
    else:
        if slug != story_obj.slugify:
            return redirect(story_obj.get_absolute_url())
        form = SubmitCommentForm()
    comments = story_obj.active_comments.prefetch_related("user", "votes")
    return render(
        request,
        "posts/story.html",
        {
            "story": story_obj,
            "comment_form": form,
            "comments": comments,
            "ongoing_reply_pk": ongoing_reply_pk,
        },
    )


@require_safe
def story_remote_content(request, story_pk, slug=None):
    try:
        story_obj = Story.objects.get(pk=story_pk)
    except Story.DoesNotExist:
        raise Http404("Story does not exist") from Story.DoesNotExist
    if slug != story_obj.slugify:
        return redirect(
            reverse(
                "story_remote_content",
                kwargs={"story_pk": story_pk, "slug": story_obj.slugify},
            )
        )
    try:
        content_obj = story_obj.remote_content
    except StoryRemoteContent.DoesNotExist:
        raise Http404(
            "Story content has not been locally cached."
        ) from StoryRemoteContent.DoesNotExist
    return HttpResponse(
        f"Remote-Url: {content_obj.url}\nRetrieved-at: {content_obj.retrieved_at}\n\n{content_obj.content}",
        content_type="text/plain; charset=utf-8",
    )


def all_stories(request, page_num=1):
    if "order_by" in request.GET:
        request.session["all_stories_order_by"] = request.GET["order_by"]
    if "ordering" in request.GET:
        request.session["all_stories_ordering"] = request.GET["ordering"]

    if page_num == 1 and request.get_full_path() != reverse("all_stories"):
        return redirect(reverse("all_stories"))

    order_by = request.session.get("all_stories_order_by", "hotness")
    ordering = request.session.get("all_stories_ordering", "desc")
    order_by_field = ("-" if ordering == "desc" else "") + order_by

    story_obj = Story.objects.filter(active=True).prefetch_related(
        "tags", "user", "comments"
    )
    if order_by == "hotness":
        stories = sorted(
            story_obj.order_by("created", "title"),
            key=lambda s: s.hotness["score"],
            reverse=ordering == "desc",
        )
    elif order_by == "last commented":
        stories = sorted(
            story_obj.order_by("created", "title"),
            key=lambda s: s.active_comments.latest("created").created
            if s.active_comments.exists()
            else s.created,
            reverse=ordering == "desc",
        )
    else:
        stories = story_obj.order_by(order_by_field, "title")

    paginator = Paginator(stories, config.STORIES_PER_PAGE)
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        # page_num is bigger than the actual number of pages
        return redirect(
            reverse("all_stories_page", kwargs={"page_num": paginator.num_pages})
        )
    order_by_form = OrderByForm(
        fields=all_stories.ORDER_BY_FIELDS,
        initial={"order_by": order_by, "ordering": ordering},
    )
    return render(
        request,
        "posts/all_stories.html",
        {
            "stories": page,
            "order_by_form": order_by_form,
            "pages": paginator.get_elided_page_range(number=page_num),
        },
    )


all_stories.ORDER_BY_FIELDS = ["hotness", "created", "last commented"]


@login_required
@transaction.atomic
def submit_story(request):
    user = request.user
    preview = None
    if request.method == "POST":
        if "fetch-title" in request.POST:
            qdict = request.POST.copy()
            if len(qdict["url"]) > 0:
                parsr = fetch_url_metadata(request, qdict["url"])
                if parsr:
                    title = parsr.title
                    qdict["title"] = title
                    if parsr.ogtitle is not None:
                        qdict["title"] = parsr.ogtitle
                    if parsr.publish_date is not None:
                        qdict["publish_date"] = parsr.publish_date
            else:
                messages.add_message(request, messages.WARNING, "URL field is empty.")
            form = SubmitStoryForm(qdict)
        elif "preview" in request.POST:
            form = SubmitStoryForm(request.POST)
            form.is_valid()
            preview = {
                "description": comment_to_html(request.POST["description"]),
                "title": form.cleaned_data["title"],
                "url": form.cleaned_data["url"],
                "domain": form.cleaned_data["url"]
                if len(form.cleaned_data["url"]) > 0
                else None,
                "publish_date": form.cleaned_data["publish_date"],
                "tags": form.cleaned_data["tags"],
            }
        else:
            form = SubmitStoryForm(request.POST)
            form.fields["title"].required = True
            if not user.has_perm("sic.add_story"):
                if user.banned_by_user is not None:
                    messages.add_message(
                        request,
                        messages.ERROR,
                        "You are banned and not allowed to submit stories.",
                    )
                else:
                    messages.add_message(
                        request,
                        messages.ERROR,
                        "You are not allowed to submit stories.",
                    )
            elif form.is_valid():
                title = form.cleaned_data["title"]
                description = form.cleaned_data["description"]
                url = form.cleaned_data["url"]
                publish_date = form.cleaned_data["publish_date"]
                user_is_author = form.cleaned_data["user_is_author"]
                new_story = Story.objects.create(
                    title=title,
                    url=url,
                    publish_date=publish_date,
                    description=description,
                    user=user,
                    user_is_author=user_is_author,
                    content_warning=form.cleaned_data["content_warning"],
                )
                new_story.tags.set(form.cleaned_data["tags"])
                new_story.kind.set(form.cleaned_data["kind"])
                new_story.save()
                return redirect(new_story.get_absolute_url())
            form.fields["title"].required = False
            error = form_errors_as_string(form.errors)
            messages.add_message(
                request, messages.ERROR, f"Invalid form. Error: {error}"
            )
    else:
        form = SubmitStoryForm(initial={"kind": StoryKind.default_value()})
    return render(
        request,
        "posts/submit.html",
        {
            "form": form,
            "preview": preview,
            "tags": {t.name: t.hex_color for t in form.fields["tags"].queryset},
            "kinds": {k.name: k.hex_color for k in form.fields["kind"].queryset},
        },
    )


@login_required
@transaction.atomic
def upvote_story(request, story_pk):
    if request.method == "POST":
        user = request.user
        try:
            story_obj = Story.objects.get(pk=story_pk)
        except Story.DoesNotExist:
            raise Http404("Story does not exist") from Story.DoesNotExist
        if story_obj.user.pk == user.pk:
            messages.add_message(
                request, messages.ERROR, "You cannot vote on your own posts."
            )
        else:
            vote, created = user.votes.get_or_create(
                story=story_obj, comment=None, user=user
            )
            if not created:
                vote.delete()
    if "next" in request.GET and check_next_url(request.GET["next"]):
        return redirect(request.GET["next"])
    return redirect(reverse("index"))


def fetch_url_metadata(request, url):
    try:
        if not check_safe_url(url):
            raise Exception(f"Invalid URL: {url}.")
        with urllib.request.urlopen(
            urllib.request.Request(
                url,
                method="GET",
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.163 Safari/537.36",
                },
            ),
            timeout=2,
        ) as response:
            final_url = response.url
            if not check_safe_url(url):
                raise Exception(f"Invalid URL: {url}.")
            text = response.read().decode("utf-8")
        parsr = TitleHTMLExtractor()
        parsr.feed(text)
        return parsr
    except Exception as exc:
        messages.add_message(
            request, messages.ERROR, f"Could not fetch title. Error: {exc}"
        )
        return None


@login_required
@transaction.atomic
def edit_story(request, story_pk, slug=None):
    user = request.user
    preview = None
    try:
        story_obj = Story.objects.get(pk=story_pk)
    except Story.DoesNotExist:
        raise Http404("Story does not exist") from Story.DoesNotExist
    if not request.user.has_perm("sic.change_story", story_obj):
        raise PermissionDenied("Only the author of the story can edit it.")
    if request.method == "POST":
        if "fetch-title" in request.POST:
            qdict = request.POST.copy()
            if len(qdict["url"]) > 0:
                parsr = fetch_url_metadata(request, qdict["url"])
                if parsr:
                    title = parsr.title
                    qdict["title"] = title
                    if parsr.ogtitle is not None:
                        qdict["title"] = parsr.ogtitle
                    if parsr.publish_date is not None:
                        qdict["publish_date"] = parsr.publish_date
            else:
                messages.add_message(request, messages.WARNING, "URL field is empty.")
            form = EditStoryForm(qdict)
        elif "preview" in request.POST:
            form = EditStoryForm(request.POST)
            form.is_valid()
            preview = {
                "description": comment_to_html(request.POST["description"]),
                "title": form.cleaned_data["title"],
                "url": form.cleaned_data["url"],
                "domain": form.cleaned_data["url"],
                "publish_date": form.cleaned_data["publish_date"],
                "tags": form.cleaned_data["tags"],
            }
        else:
            form = EditStoryForm(request.POST)
            if form.is_valid():
                title_before = story_obj.title
                desc_before = story_obj.description
                url_before = story_obj.url
                cw_before = story_obj.content_warning
                pubdate_before = story_obj.publish_date
                tags_before = list(story_obj.tags.all())
                kinds_before = list(story_obj.kind.all())

                story_obj.title = form.cleaned_data["title"]
                story_obj.description = form.cleaned_data["description"]
                story_obj.url = form.cleaned_data["url"]
                story_obj.user_is_author = form.cleaned_data["user_is_author"]
                story_obj.tags.set(form.cleaned_data["tags"])
                story_obj.kind.set(form.cleaned_data["kind"])
                story_obj.publish_date = form.cleaned_data["publish_date"]
                story_obj.content_warning = form.cleaned_data["content_warning"]

                if title_before != form.cleaned_data["title"]:
                    ModerationLogEntry.edit_story_title(
                        title_before, story_obj, user, form.cleaned_data["reason"]
                    )
                if desc_before != form.cleaned_data["description"]:
                    ModerationLogEntry.edit_story_desc(
                        desc_before, story_obj, user, form.cleaned_data["reason"]
                    )
                if url_before != form.cleaned_data["url"]:
                    ModerationLogEntry.edit_story_url(
                        url_before, story_obj, user, form.cleaned_data["reason"]
                    )
                if cw_before != form.cleaned_data["content_warning"]:
                    ModerationLogEntry.edit_story_cw(
                        cw_before, story_obj, user, form.cleaned_data["reason"]
                    )
                if pubdate_before != form.cleaned_data["publish_date"]:
                    ModerationLogEntry.edit_story_pubdate(
                        pubdate_before, story_obj, user, form.cleaned_data["reason"]
                    )
                if tags_before != list(form.cleaned_data["tags"]):
                    ModerationLogEntry.edit_story_tags(
                        tags_before, story_obj, user, form.cleaned_data["reason"]
                    )
                if kinds_before != list(form.cleaned_data["kind"]):
                    ModerationLogEntry.edit_story_kind(
                        kinds_before, story_obj, user, form.cleaned_data["reason"]
                    )

                story_obj.save()
                return redirect(story_obj.get_absolute_url())
            error = form_errors_as_string(form.errors)
            messages.add_message(
                request, messages.ERROR, f"Invalid form. Error: {error}"
            )
    else:
        form = EditStoryForm(
            initial={
                "title": story_obj.title,
                "description": story_obj.description,
                "url": story_obj.url,
                "publish_date": story_obj.publish_date,
                "user_is_author": story_obj.user_is_author,
                "tags": story_obj.tags.all(),
                "kind": story_obj.kind.all(),
                "content_warning": story_obj.content_warning,
            }
        )
    return render(
        request,
        "posts/submit.html",
        {
            "form": form,
            "preview": preview,
            "story": story_obj,
            "tags": {t.name: t.hex_color for t in form.fields["tags"].queryset},
            "kinds": {k.name: k.hex_color for k in form.fields["kind"].queryset},
        },
    )


class TitleHTMLExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.ogtitle = None
        self.publish_date = None
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True
        elif tag == "meta":
            attrs = {a[0]: a[1] for a in attrs}
            if (
                "content" in attrs
                and "property" in attrs
                and attrs["property"] == "article:published_time"
            ):
                try:
                    if attrs["content"].endswith("Z"):
                        attrs["content"] = attrs["content"][:-1]
                    self.publish_date = datetime.fromisoformat(attrs["content"]).date()
                except:
                    pass
            if (
                "content" in attrs
                and "property" in attrs
                and attrs["property"] == "og:title"
            ):
                self.ogtitle = attrs["content"]

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data
