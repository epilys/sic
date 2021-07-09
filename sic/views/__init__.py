from django.http import Http404
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.contrib import messages
from django.db.models import Exists, OuterRef
from django.core.paginator import Paginator, InvalidPage
from django.core.exceptions import PermissionDenied
from ..models import Story, StoryKind, Comment, User, Invitation
from ..forms import SubmitCommentForm, SubmitReplyForm, SubmitStoryForm


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
    if request.method == "POST":
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
    paginator = Paginator(story_obj.order_by("-created", "title"), 10)
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
    paginator = Paginator(story_obj[:40], 10)
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
    paginator = Paginator(comments[:40], 10)
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
