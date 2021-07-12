from http import HTTPStatus
from django.http import Http404, HttpResponse
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.contrib import messages
from django.db.models import Exists, OuterRef
from django.core.paginator import Paginator, InvalidPage
from django.core.exceptions import PermissionDenied
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_http_methods
from ..models import Story, StoryKind, Comment, User, Invitation
from ..forms import SubmitCommentForm, SubmitReplyForm, SubmitStoryForm
from ..apps import SicAppConfig as config
from ..markdown import comment_to_html


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
                    parent_user = story_obj.user
                    parent_user.notify_reply(new, request)
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
    if request.user.is_authenticated:
        # Annotate each comment with whether the logged in user has upvoted it or not.
        comments = comments.annotate(
            upvoted=Exists(
                request.user.votes.filter(story=story_obj, comment=OuterRef("pk"))
            )
        )
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
            parent_user = comment.user
            comment = Comment.objects.create(
                user=user, story=comment.story, parent=comment, text=text
            )
            parent_user.notify_reply(comment, request)
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
    if page_num == 1 and request.get_full_path() != "/":
        # Redirect to '/' to avoid having both '/' and '/page/1' as valid urls.
        return redirect(reverse("index"))
    story_obj = Story.objects.filter(active=True)
    if request.user.is_authenticated:
        # Annotate each story with whether the logged in user has upvoted it or not.
        story_obj = story_obj.annotate(
            upvoted=Exists(
                request.user.votes.filter(story=OuterRef("pk"), comment=None)
            )
        )
    paginator = Paginator(
        story_obj.order_by("-created", "title"), config.STORIES_PER_PAGE
    )
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        # page_num is bigger than the actual number of pages
        return redirect(reverse("index_page", kwargs={"page_num": paginator.num_pages}))
    return render(request, "index.html", {"stories": page})


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
    if request.user.is_authenticated:
        # Annotate each story with whether the logged in user has upvoted it or not.
        story_obj = story_obj.annotate(
            upvoted=Exists(
                request.user.votes.filter(story=OuterRef("pk"), comment=None)
            )
        )
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
    if request.user.is_authenticated:
        # Annotate each story with whether the logged in user has upvoted it or not.
        comments = comments.annotate(
            upvoted=Exists(request.user.votes.filter(comment=OuterRef("pk")))
        )
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


def about(request):
    return render(request, "about.html")


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


@require_http_methods(
    [
        "GET",
    ]
)
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
