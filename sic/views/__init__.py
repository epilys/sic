from http import HTTPStatus
from django.http import Http404, HttpResponse
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
from ..forms import (
    SubmitCommentForm,
    SubmitReplyForm,
    SubmitStoryForm,
    SearchCommentsForm,
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


def story(request, story_pk, slug=None):
    try:
        story_obj = Story.objects.get(pk=story_pk)
    except Story.DoesNotExist:
        raise Http404("Story does not exist") from Story.DoesNotExist
    if "reply_preview" in request.session:
        request.session["reply_preview"] = {}
    request.session.modified = True
    ongoing_reply_form = None
    ongoing_reply_pk = None
    if request.method == "POST":
        if "preview" in request.POST:
            form = SubmitCommentForm()
            if "preview_comment_pk" in request.POST:
                comment_pk = request.POST["preview_comment_pk"]
                ongoing_reply_form = SubmitReplyForm(request.POST)
            else:
                comment_pk = None
                form = SubmitCommentForm(request.POST)
                ongoing_reply_form = None
            text = request.POST["text"]
            if "reply_preview" not in request.session:
                request.session["reply_preview"] = {}
            request.session["reply_preview"][comment_pk] = comment_to_html(text)
            request.session.modified = True
            ongoing_reply_pk = int(comment_pk) if comment_pk else None
            messages.add_message(
                request,
                messages.INFO,
                "You can view the formatting preview above the comment form.",
            )
        else:
            form = SubmitCommentForm(request.POST)
            if form.is_valid():
                if request.user:
                    new = Comment.objects.create(
                        user=request.user,
                        story=story_obj,
                        parent=None,
                        text=form.cleaned_data["text"],
                    )
                    new.save()
                    messages.add_message(
                        request, messages.SUCCESS, "Your comment was posted."
                    )
                    form = SubmitCommentForm()
                else:
                    messages.add_message(
                        request, messages.ERROR, "You must be logged in to comment."
                    )
            else:
                error = form_errors_as_string(form.errors)
                messages.add_message(
                    request, messages.ERROR, f"Invalid comment form. Error: {error}"
                )
    else:
        if slug != story_obj.slugify():
            return redirect(story_obj.get_absolute_url())
        form = SubmitCommentForm()
    reply_form = SubmitReplyForm()
    comments = Comment.objects.filter(story=story_obj, parent=None)
    return render(
        request,
        "story.html",
        {
            "story": story_obj,
            "comment_form": form,
            "reply_form": reply_form,
            "comments": comments,
            "ongoing_reply_form": ongoing_reply_form,
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
        form = SubmitReplyForm(request.POST)
        if form.is_valid():
            text = form.cleaned_data["text"]
            comment = Comment.objects.create(
                user=user, story=comment.story, parent=comment, text=text
            )
            messages.add_message(
                request, messages.SUCCESS, "You successfuly submitted a comment."
            )
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
        user = request.user
        if user.taggregation_subscriptions.exists():
            has_subscriptions = True
            story_obj = Story.objects.none().union(
                *list(
                    map(
                        lambda t: t.get_stories(), user.taggregation_subscriptions.all()
                    )
                )
            )
            taggregations = list(user.taggregation_subscriptions.all())
            if len(taggregations) > 5:
                others = taggregations[5:]
                taggregations = taggregations[:5]
            else:
                others = None
            taggregations = {
                "list": taggregations,
                "others": others,
            }
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
    if request.method == "POST":
        form = SubmitStoryForm(request.POST)
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
        error = form_errors_as_string(form.errors)
        messages.add_message(request, messages.ERROR, f"Invalid form. Error: {error}")
    else:
        form = SubmitStoryForm(initial={"kind": StoryKind.default_value()})
    return render(request, "submit.html", {"form": form})


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
def edit_story(request, story_pk, slug=None):
    user = request.user
    try:
        story_obj = Story.objects.get(pk=story_pk)
    except Story.DoesNotExist:
        raise Http404("Story does not exist") from Story.DoesNotExist
    if story_obj.user != user:
        raise PermissionDenied("You are not the author of this story.")
    if request.method == "POST":
        form = SubmitStoryForm(request.POST)
        if form.is_valid():
            story_obj.title = form.cleaned_data["title"]
            story_obj.description = form.cleaned_data["description"]
            story_obj.url = form.cleaned_data["url"]
            story_obj.user_is_author = form.cleaned_data["user_is_author"]
            story_obj.tags.set(form.cleaned_data["tags"])
            story_obj.save()
            return redirect(story_obj.get_absolute_url())
        error = form_errors_as_string(form.errors)
        messages.add_message(request, messages.ERROR, f"Invalid form. Error: {error}")
    else:
        form = SubmitStoryForm(
            initial={
                "title": story_obj.title,
                "description": story_obj.description,
                "url": story_obj.url,
                "user_is_author": story_obj.user_is_author,
                "tags": story_obj.tags.all(),
            }
        )
    return render(request, "submit.html", {"form": form})


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
    reply_form = SubmitReplyForm()
    return render(
        request, "recent_comments.html", {"comments": page, "reply_form": reply_form}
    )


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
