import urllib.request
from http import HTTPStatus
from django.http import Http404, HttpResponse, HttpResponseForbidden, HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.contrib import messages
from django.core.paginator import Paginator, InvalidPage
from django.core.exceptions import PermissionDenied
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_http_methods
from ..models import Story, StoryKind, Comment, User, Invitation
from ..moderation import ModerationLogEntry
from ..forms import (
    SubmitCommentForm,
    EditReplyForm,
    DeleteCommentForm,
    SubmitStoryForm,
    SearchCommentsForm,
    BanUserForm,
)
from ..apps import SicAppConfig as config
from ..markdown import comment_to_html
from ..search import query_comments


class HttpResponseNotImplemented(HttpResponse):
    status_code = HTTPStatus.NOT_IMPLEMENTED


def form_errors_as_string(errors):
    return ", ".join(
        map(lambda k: ", ".join(map(lambda err: k + ": " + err, errors[k])), errors)
    )


from .account import *
from .tags import *


@login_required
def preview_comment(request):
    if "next" not in request.GET:
        return HttpResponseBadRequest("Request url should have a ?next= GET parameter.")
    if "comment_preview" in request.session:
        request.session["comment_preview"] = {}
    # The preview is saved in the user's session, and then retrieved in
    # the template by the tag `get_comment_preview` located in
    # sic/templatetags/utils.py which puts the preview in the rendering
    # context.
    comment = None
    try:
        comment_pk = request.POST.get("preview_comment_pk", None)
        if comment_pk:
            comment = Comment.objects.get(pk=comment_pk)
        else:
            comment_pk = "null"
        text = request.POST["text"]
        request.session["comment_preview"] = {comment_pk: {}}
        request.session["comment_preview"][comment_pk]["input"] = text
        request.session["comment_preview"][comment_pk]["html"] = comment_to_html(text)
        request.session.modified = True
        if comment:
            return redirect(request.GET["next"] + "#" + comment.slugify())
        else:
            return redirect(request.GET["next"])
    except (Comment.DoesNotExist, KeyError):
        return redirect(request.GET["next"])


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
        if not request.user.is_authenticated:
            messages.add_message(
                request, messages.ERROR, "You must be logged in to comment."
            )
        else:
            form = SubmitCommentForm(request.POST)
            if form.is_valid():
                comment = Comment.objects.create(
                    user=request.user,
                    story=story_obj,
                    parent=None,
                    text=form.cleaned_data["text"],
                )
                request.session["comment_preview"] = {}
                return redirect(comment)
            else:
                error = form_errors_as_string(form.errors)
                messages.add_message(
                    request, messages.ERROR, f"Invalid comment form. Error: {error}"
                )
    else:
        if slug != story_obj.slugify():
            return redirect(story_obj.get_absolute_url())
        form = SubmitCommentForm()
    comments = story_obj.comments.filter(parent=None)
    return render(
        request,
        "story.html",
        {
            "story": story_obj,
            "comment_form": form,
            "comments": comments,
            "ongoing_reply_pk": ongoing_reply_pk,
        },
    )


@login_required
def reply(request, comment_pk):
    user = request.user
    try:
        comment = Comment.objects.get(pk=comment_pk)
    except Comment.DoesNotExist:
        raise Http404("Comment does not exist") from Comment.DoesNotExist
    if request.method == "POST":
        form = SubmitCommentForm(request.POST)
        if form.is_valid():
            text = form.cleaned_data["text"]
            comment = Comment.objects.create(
                user=user, story=comment.story, parent=comment, text=text
            )
            request.session["comment_preview"] = {}
            return redirect(comment)
        else:
            error = form_errors_as_string(form.errors)
            messages.add_message(
                request, messages.ERROR, f"Invalid form. Error: {error}"
            )
    return redirect(comment.story.get_absolute_url())


def index(request, page_num=1):
    if page_num == 1 and request.get_full_path() != reverse("index"):
        # Redirect to '/' to avoid having both '/' and '/page/1' as valid urls.
        return redirect(reverse("index"))
    story_obj = None
    taggregations = None
    has_subscriptions = False
    # Figure out what to show in the index
    # If user is authenticated AND has subscribed aggregations, show the set union of them
    # otherwise show every story.
    if request.user.is_authenticated:
        frontpage = request.user.frontpage()
        story_obj = frontpage["stories"]
        taggregations = frontpage["taggregations"]
        has_subscriptions = taggregations is not None
    if not story_obj:
        story_obj = Story.objects.filter(active=True)
    all_stories = sorted(
        story_obj.order_by("-created", "title"),
        key=lambda s: s.hotness()["score"],
        reverse=True,
    )
    paginator = Paginator(all_stories, config.STORIES_PER_PAGE)
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        # page_num is bigger than the actual number of pages
        return redirect(reverse("index_page", kwargs={"page_num": paginator.num_pages}))
    return render(
        request,
        "index.html",
        {
            "stories": page,
            "has_subscriptions": has_subscriptions,
            "aggregations": taggregations,
        },
    )


def all_stories(request, page_num=1):
    if page_num == 1 and request.get_full_path() != reverse("all_stories"):
        return redirect(reverse("all_stories"))
    story_obj = Story.objects.filter(active=True)
    all_stories = sorted(
        story_obj.order_by("-created", "title"),
        key=lambda s: s.hotness()["score"],
        reverse=True,
    )
    paginator = Paginator(all_stories, config.STORIES_PER_PAGE)
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        # page_num is bigger than the actual number of pages
        return redirect(
            reverse("all_stories_page", kwargs={"page_num": paginator.num_pages})
        )
    return render(request, "all_stories.html", {"stories": page})


@login_required
def submit_story(request):
    user = request.user
    preview = None
    if request.method == "POST":
        if "fetch-title" in request.POST:
            qdict = request.POST.copy()
            if len(qdict["url"]) > 0:
                try:
                    with urllib.request.urlopen(qdict["url"], timeout=2) as r:
                        text = r.read().decode("utf-8")
                    parsr = TitleHTMLExtractor()
                    parsr.feed(text)
                    title = parsr.title
                    qdict["title"] = title
                except Exception as exc:
                    messages.add_message(
                        request, messages.ERROR, f"Could not fetch title. Error: {exc}"
                    )
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
            if form.is_valid():
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
                )
                new_story.tags.set(form.cleaned_data["tags"])
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
        "submit.html",
        {
            "form": form,
            "preview": preview,
        },
    )


@login_required
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
    if "next" in request.GET:
        return redirect(request.GET["next"])
    return redirect(reverse("index"))


@login_required
def edit_comment(request, comment_pk):
    user = request.user
    try:
        comment_obj = Comment.objects.get(pk=comment_pk)
    except Comment.DoesNotExist:
        raise Http404("Comment does not exist") from Comment.DoesNotExist

    if (
        not request.user.is_admin
        and not request.user.is_moderator
        and request.user != comment_obj.user
    ):
        raise PermissionDenied("Only a comment author or a moderator may edit it.")

    if request.method == "POST":
        form = EditReplyForm(request.POST)
        if form.is_valid():
            before_text = comment_obj.text
            reason = form.cleaned_data["edit_reason"] or ""
            if comment_obj.user != request.user and not reason:
                messages.add_message(
                    request,
                    messages.ERROR,
                    "A reason is required in order to edit someone else's comment!",
                )
            else:
                ModerationLogEntry.edit_comment(
                    before_text, comment_obj, request.user, reason
                )
                comment_obj.text = form.cleaned_data["text"]
                comment_obj.save()
                return redirect(comment_obj)
            return redirect(comment_obj.story.get_absolute_url())
        else:
            error = form_errors_as_string(form.errors)
            messages.add_message(
                request, messages.ERROR, f"Invalid form. Error: {error}"
            )
            return redirect(comment_obj.story.get_absolute_url())
    else:
        form = EditReplyForm(
            initial={
                "text": comment_obj.text,
            },
        )
        return render(
            request,
            "edit_comment.html",
            {
                "story": comment_obj.story,
                "comment": comment_obj,
                "form": form,
            },
        )


@login_required
def delete_comment(request, comment_pk):
    user = request.user
    try:
        comment_obj = Comment.objects.get(pk=comment_pk)
    except Comment.DoesNotExist:
        raise Http404("Comment does not exist") from Comment.DoesNotExist

    if (
        not request.user.is_admin
        and not request.user.is_moderator
        and request.user != comment_obj.user
    ):
        raise PermissionDenied(
            "Only a comment author or a moderator may delete this comment."
        )

    if request.method == "POST":
        form = DeleteCommentForm(request.POST)
        if form.is_valid():
            comment_obj.deleted = True
            reason = form.cleaned_data["deletion_reason"] or ""
            if comment_obj.user != request.user and not reason:
                messages.add_message(
                    request,
                    messages.ERROR,
                    "A reason is required in order to delete someone else's comment!",
                )
            else:
                ModerationLogEntry.delete_comment(
                    comment_obj, request.user, form.cleaned_data["deletion_reason"]
                )
                comment_obj.save()
                messages.add_message(
                    request,
                    messages.SUCCESS,
                    f"Your comment (id: {comment_obj.pk}) has been deleted.",
                )
        else:
            error = form_errors_as_string(form.errors)
            messages.add_message(
                request, messages.ERROR, f"Invalid form. Error: {error}"
            )
    else:
        form = DeleteCommentForm()
        return render(
            request,
            "edit_comment.html",
            {
                "story": comment_obj.story,
                "comment": comment_obj,
                "edit_comment_pk": comment_pk,
                "delete_comment": True,
                "delete_comment_form": form,
            },
        )

    return redirect(comment_obj.story.get_absolute_url())


@login_required
def edit_story(request, story_pk, slug=None):
    user = request.user
    preview = None
    try:
        story_obj = Story.objects.get(pk=story_pk)
    except Story.DoesNotExist:
        raise Http404("Story does not exist") from Story.DoesNotExist
    if not request.user.has_perm("sic.change_story"):
        raise PermissionDenied("Only the author of the story can edit it.")
    if request.method == "POST":
        if "fetch-title" in request.POST:
            qdict = request.POST.copy()
            if len(qdict["url"]) > 0:
                try:
                    with urllib.request.urlopen(qdict["url"], timeout=2) as r:
                        text = r.read().decode("utf-8")
                    parsr = TitleHTMLExtractor()
                    parsr.feed(text)
                    title = parsr.title
                    qdict["title"] = title
                except Exception as exc:
                    messages.add_message(
                        request, messages.ERROR, f"Could not fetch title. Error: {exc}"
                    )
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
                "domain": form.cleaned_data["url"],
                "publish_date": form.cleaned_data["publish_date"],
                "tags": form.cleaned_data["tags"],
            }
        else:
            form = SubmitStoryForm(request.POST)
            if form.is_valid():
                story_obj.title = form.cleaned_data["title"]
                story_obj.description = form.cleaned_data["description"]
                story_obj.url = form.cleaned_data["url"]
                story_obj.user_is_author = form.cleaned_data["user_is_author"]
                story_obj.tags.set(form.cleaned_data["tags"])
                story_obj.kind.set(form.cleaned_data["kind"])
                story_obj.save()
                return redirect(story_obj.get_absolute_url())
            error = form_errors_as_string(form.errors)
            messages.add_message(
                request, messages.ERROR, f"Invalid form. Error: {error}"
            )
    else:
        form = SubmitStoryForm(
            initial={
                "title": story_obj.title,
                "description": story_obj.description,
                "url": story_obj.url,
                "publish_date": story_obj.publish_date,
                "user_is_author": story_obj.user_is_author,
                "tags": story_obj.tags.all(),
                "kind": story_obj.kind.all(),
            }
        )
    return render(
        request,
        "submit.html",
        {
            "form": form,
            "preview": preview,
            "story": story_obj,
        },
    )


@login_required
def upvote_comment(request, story_pk, slug, comment_pk):
    if request.method == "POST":
        user = request.user
        try:
            story_obj = Story.objects.get(pk=story_pk)
        except Story.DoesNotExist:
            raise Http404("Story does not exist") from Story.DoesNotExist
        try:
            comment_obj = Comment.objects.get(pk=comment_pk)
        except Comment.DoesNotExist:
            raise Http404("Comment does not exist") from Comment.DoesNotExist
        if comment_obj.user.pk == user.pk:
            messages.add_message(
                request, messages.ERROR, "You cannot vote on your own posts."
            )
        else:
            vote, created = user.votes.filter(story=story_obj).get_or_create(
                story=story_obj, comment=comment_obj, user=user
            )
            if not created:
                vote.delete()
    if "next" in request.GET:
        return redirect(request.GET["next"])
    return redirect(reverse("index"))


def recent(request, page_num=1):
    if page_num == 1 and request.get_full_path() != reverse("recent"):
        # Redirect to '/' to avoid having both '/' and '/page/1' as valid urls.
        return redirect(reverse("recent"))
    story_obj = Story.objects.order_by("-created", "title").filter(active=True)
    paginator = Paginator(story_obj[:40], config.STORIES_PER_PAGE)
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        # page_num is bigger than the actual number of pages
        return redirect(
            reverse("recent_page", kwargs={"page_num": paginator.num_pages})
        )
    return render(request, "index.html", {"stories": page})


def recent_comments(request, page_num=1):
    if page_num == 1 and request.get_full_path() != reverse("recent_comments"):
        # Redirect to '/' to avoid having both '/' and '/page/1' as valid urls.
        return redirect(reverse("recent_comments"))
    comments = Comment.objects.order_by("-created").filter(deleted=False)
    paginator = Paginator(comments[:40], config.STORIES_PER_PAGE)
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        # page_num is bigger than the actual number of pages
        return redirect(
            reverse("recent_comments_page", kwargs={"page_num": paginator.num_pages})
        )
    return render(request, "recent_comments.html", {"comments": page})


@cache_page(60 * 15)
def invitation_tree(request):
    root_user = User.objects.earliest("created")

    return render(
        request,
        "about_invitation_tree.html",
        {
            "root_user": root_user,
            "depth": 0,
            "max_depth": 64,
        },
    )


@require_http_methods(["GET"])
def comment_source(request, story_pk, slug, comment_pk):
    try:
        story_obj = Story.objects.get(pk=story_pk)
    except Story.DoesNotExist:
        raise Http404("Story does not exist") from Story.DoesNotExist
    try:
        comment_obj = Comment.objects.get(pk=comment_pk)
    except Comment.DoesNotExist:
        raise Http404("Comment does not exist") from Comment.DoesNotExist
    return HttpResponse(comment_obj.text, content_type="text/plain; charset=utf-8")


@require_http_methods(["GET"])
def search(request):
    results = None
    if "text" in request.GET:
        form = SearchCommentsForm(request.GET)
        if form.is_valid():
            results = query_comments(form.cleaned_data["text"])
    else:
        form = SearchCommentsForm()
    return render(request, "search.html", {"form": form, "results": results})


from html.parser import HTMLParser


class TitleHTMLExtractor(HTMLParser):
    def __init__(self):
        super(TitleHTMLExtractor, self).__init__()
        self.title = ""
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        if tag == "title":
            self.in_title = True

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


@require_http_methods(["GET"])
def moderation_log(request, page_num=1):
    if page_num == 1 and request.get_full_path() != reverse("moderation_log"):
        return redirect(reverse("moderation_log"))
    logs = ModerationLogEntry.objects.order_by("-action_time")
    paginator = Paginator(logs, 10)
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        # page_num is bigger than the actual number of pages
        return redirect(
            reverse("moderation_log_page", kwargs={"page_num": paginator.num_pages})
        )
    return render(
        request,
        "moderation_log.html",
        {
            "logs": page,
        },
    )


@login_required
def moderation(request):
    if (not request.user.is_moderator) and (not request.user.is_admin):
        return HttpResponseForbidden()
    if request.method == "POST":
        if "set-ban" in request.POST:
            ban_user_form = BanUserForm(request.POST)
            if ban_user_form.is_valid():
                user = ban_user_form.cleaned_data["username"]
                ban = ban_user_form.cleaned_data["ban"]
                reason = ban_user_form.cleaned_data["reason"]
                if ban and user.banned_by_user is not None:
                    messages.add_message(
                        request, messages.ERROR, f"{user} already banned"
                    )
                    return redirect(reverse("moderation"))
                if not ban and user.banned_by_user is None:
                    messages.add_message(
                        request, messages.ERROR, f"{user} already not banned"
                    )
                    return redirect(reverse("moderation"))
                user.banned_by_user = request.user if ban else None
                user.save()
                log_entry = ModerationLogEntry.changed_user_status(
                    user,
                    request.user,
                    "Banned user" if ban else "Unbanned user",
                    reason,
                )
                messages.add_message(
                    request, messages.SUCCESS, f"{log_entry.action} {user}"
                )
                return redirect(reverse("moderation"))
            error = form_errors_as_string(ban_user_form.errors)
            messages.add_message(
                request, messages.ERROR, f"Invalid form. Error: {error}"
            )
        else:
            ban_user_form = BanUserForm()
    else:
        ban_user_form = BanUserForm()
    return render(request, "moderation.html", {"ban_user_form": ban_user_form})
