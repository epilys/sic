from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.contrib import messages
from django.db.models import Exists, OuterRef, Value, BooleanField
from django.core.paginator import Paginator, InvalidPage
from .models import Story, Comment, User, Invitation
from .forms import *

from wand.image import Image
from PIL import Image as PILImage


def form_errors_as_string(errors):
    return ", ".join(
        map(lambda k: ", ".join(map(lambda err: k + ": " + err, errors[k])), errors)
    )


def story(request, pk, slug=None):
    try:
        s = Story.objects.get(pk=pk)
    except Story.DoesNotExist:
        raise Http404("Story does not exist")
    if request.method == "POST":
        form = SubmitCommentForm(request.POST)
        if form.is_valid():
            if request.user:
                new = Comment.objects.create(
                    user=request.user,
                    story=s,
                    parent=None,
                    text=form.cleaned_data["text"],
                )
                new.save()
                messages.add_message(
                    request, messages.SUCCESS, f"Your comment was posted."
                )
            else:
                messages.add_message(
                    request, messages.ERROR, f"You must be logged in to comment."
                )
        else:
            error = form_errors_as_string(form.errors)
            messages.add_message(
                request, messages.ERROR, f"Invalid comment form. Error: {error}"
            )
    else:
        if slug != s.slugify():
            return redirect(s.get_absolute_url())
        form = SubmitCommentForm()
    reply_form = SubmitReplyForm()
    if request.user.is_authenticated:
        """
        Annotate each comment with whether the logged in user has upvoted it or not.
        """
        comments = Comment.objects.filter(story=s, parent=None).annotate(
            upvoted=Exists(request.user.votes.filter(story=s, comment=OuterRef("pk")))
        )
    else:
        comments = Comment.objects.filter(story=s, parent=None)
    return render(
        request,
        "story.html",
        {
            "story": s,
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
        raise Http404("Comment does not exist")
    if request.method == "POST":
        form = SubmitReplyForm(request.POST)
        if form.is_valid():
            text = form.cleaned_data["text"]
            new_comment = Comment.objects.create(
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
        """
        Redirect to '/' to avoid having both '/' and '/page/1' as valid urls.
        """
        return redirect(reverse("index"))
    if request.user.is_authenticated:
        """
        Annotate each story with whether the logged in user has upvoted it or not.
        """
        s = (
            Story.objects.all()
            .filter(active=True)
            .annotate(
                upvoted=Exists(
                    request.user.votes.all().filter(story=OuterRef("pk"), comment=None)
                )
            )
        )
    else:
        s = Story.objects.all().filter(active=True)
    if not s.exists():
        if request.get_full_path() != "/":
            return redirect(reverse("index"))
        s = Story.objects.none()
    paginator = Paginator(s.order_by("-created", "title"), 10)
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        """
        page_num is bigger than the actual number of pages
        """
        return redirect(reverse("index_page", kwargs={"page_num": paginator.num_pages}))
    return render(request, "index.html", {"stories": page})


def login(request):
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            return redirect(reverse("index"))
        else:
            messages.add_message(request, messages.ERROR, f"Could not login.")
    return render(request, "login.html")


@login_required
def account(request):
    generate_invite_form = GenerateInviteForm()
    return render(
        request,
        "account.html",
        {"user": request.user, "generate_invite_form": generate_invite_form},
    )


@login_required
def edit_profile(request):
    user = request.user
    if request.method == "POST":
        form = EditProfileForm(request.POST)
        if form.is_valid():
            homepage = form.cleaned_data["homepage"]
            git_repository = form.cleaned_data["git_repository"]
            about = form.cleaned_data["about"]
            request.user.homepage = homepage
            request.user.about = about
            request.user.save()
            return redirect(reverse("account"))
        else:
            error = form_errors_as_string(form.errors)
            messages.add_message(
                request, messages.ERROR, f"Invalid form. Error: {error}"
            )
    else:
        initial = {
            "homepage": user.homepage,
            "git_repository": user.github_username,
            "about": user.about,
        }
        form = EditProfileForm(initial=initial)
    return render(request, "edit_profile.html", {"user": request.user, "form": form})


@login_required
def edit_avatar(request):
    """Convert image to data:image/... in order to save avatars as strings in database."""

    def generate_image_thumbnail(blob):
        with Image(blob=blob) as i:
            with i.convert("webp") as page:
                page.alpha_channel = False
                width = page.width
                height = page.height
                ratio = 100.0 / (width * 1.0)
                new_height = int(ratio * height)
                page.thumbnail(width=100, height=new_height)
                return page.data_url()

    if request.method == "POST":
        form = EditAvatarForm(request.POST, request.FILES)
        if form.is_valid():
            img = form.cleaned_data["new_avatar"]
            print(img)
            data_url = generate_image_thumbnail(img)
            request.user.avatar = data_url
            request.user.save()
            return redirect(reverse("account"))
        else:
            error = form_errors_as_string(form.errors)
            messages.add_message(
                request, messages.ERROR, f"Invalid form. Error: {error}"
            )
    else:
        form = EditAvatarForm()
    return render(request, "edit_avatar.html", {"user": request.user, "form": form})


def profile(request, username):
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        try:
            user = User.objects.get(pk=int(username))
        except:
            raise Http404("User does not exist")
    return render(request, "profile.html", {"user": user})


@login_required
def inbox(request):
    user = request.user
    messages = list(user.received_messages.all()) + list(user.sent_messages.all())
    return render(request, "inbox.html", {"messages": messages})


@login_required
def submit_story(request):
    user = request.user
    if request.method == "POST":
        form = SubmitStoryForm(request.POST)
        if form.is_valid():
            title = form.cleaned_data["title"]
            description = form.cleaned_data["description"]
            url = form.cleaned_data["url"]
            user_is_author = form.cleaned_data["user_is_author"]
            story = Story.objects.create(
                title=title,
                url=url,
                description=description,
                user=user,
                user_is_author=user_is_author,
            )
            story.tags.set(form.cleaned_data["tags"])
            story.save()
            return redirect(story.get_absolute_url())
        else:
            error = form_errors_as_string(form.errors)
            messages.add_message(
                request, messages.ERROR, f"Invalid form. Error: {error}"
            )
    else:
        form = SubmitStoryForm()
    return render(request, "submit.html", {"form": form})


@login_required
def upvote_story(request, pk):
    if request.method == "POST":
        user = request.user
        try:
            s = Story.objects.get(pk=pk)
        except Story.DoesNotExist:
            raise Http404("Story does not exist")
        if s.user.pk == user.pk:
            messages.add_message(
                request, messages.ERROR, "You cannot vote on your own posts."
            )
        else:
            vote, created = user.votes.all().get_or_create(
                story=s, comment=None, user=user
            )
            if not created:
                vote.delete()
    if "next" in request.GET:
        return redirect(request.GET["next"])
    return redirect(reverse("index"))


@login_required
def generate_invite(request):
    if request.method == "POST":
        user = request.user
        form = GenerateInviteForm(request.POST)
        if form.is_valid():
            address = form.cleaned_data["email"]
            invitation, created = user.invited.all().get_or_create(
                inviter=user, address=address
            )
            if created:
                messages.add_message(
                    request,
                    messages.SUCCESS,
                    f"Successfully generated invitation to {address}.",
                )
        else:
            error = form_errors_as_string(form.errors)
            messages.add_message(
                request, messages.ERROR, f"Invalid form. Error: {error}"
            )
    if "next" in request.GET:
        return redirect(request.GET["next"])
    return redirect(reverse("account"))


def profile_posts(request, username, page_num=1):
    print("profile_posts", username, page_num)
    if page_num == 1 and request.get_full_path() != reverse(
        "profile_posts", args=[username]
    ):
        return redirect(reverse("profile_posts", args=[username]))
    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        raise Http404("User does not exist")
    s = list(
        user.stories.filter(active=True)
        .annotate(is_story=Value("True", output_field=BooleanField()))
        .order_by("-created", "title")
    ) + list(
        user.comments.filter(deleted=False)
        .annotate(is_story=Value("False", output_field=BooleanField()))
        .order_by("-created")
    )
    s = sorted(s, key=lambda x: x.created, reverse=True)
    paginator = Paginator(s, 10)
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        """
        page_num BooleanFieldis bigger than the actual number of pages
        """
        return redirect(
            reverse(
                "profile_posts_page",
                args=[username],
                kwargs={"page_num": paginator.num_pages},
            )
        )
    print(s)
    return render(
        request,
        "profile_posts.html",
        {"posts": page, "reply_form": SubmitReplyForm(), "user": user},
    )


@login_required
def edit_story(request, pk, slug=None):
    user = request.user
    try:
        s = Story.objects.get(pk=pk)
    except Story.DoesNotExist:
        raise Http404("Story does not exist")
    if request.method == "POST":
        form = SubmitStoryForm(request.POST)
        if form.is_valid():
            s.title = form.cleaned_data["title"]
            s.description = form.cleaned_data["description"]
            s.url = form.cleaned_data["url"]
            s.user_is_author = form.cleaned_data["user_is_author"]
            s.tags.set(form.cleaned_data["tags"])
            s.save()
            return redirect(s.get_absolute_url())
        else:
            error = form_errors_as_string(form.errors)
            messages.add_message(
                request, messages.ERROR, f"Invalid form. Error: {error}"
            )
    else:
        form = SubmitStoryForm(
            initial={
                "title": s.title,
                "description": s.description,
                "url": s.url,
                "user_is_author": s.user_is_author,
                "tags": s.tags.all(),
            }
        )
    return render(request, "submit.html", {"form": form})


@login_required
def upvote_comment(request, story_pk, slug, comment_pk):
    if request.method == "POST":
        user = request.user
        try:
            s = Story.objects.get(pk=story_pk)
        except Story.DoesNotExist:
            raise Http404("Story does not exist")
        try:
            c = Comment.objects.get(pk=comment_pk)
        except Comment.DoesNotExist:
            raise Http404("Comment does not exist")
        if c.user.pk == user.pk:
            messages.add_message(
                request, messages.ERROR, "You cannot vote on your own posts."
            )
        else:
            vote, created = user.votes.filter(story=s).get_or_create(
                story=s, comment=c, user=user
            )
            if not created:
                vote.delete()
    if "next" in request.GET:
        return redirect(request.GET["next"])
    return redirect(reverse("index"))


def accept_invite(request, pk):
    try:
        inv = Invitation.objects.get(pk=pk)
    except Invitation.DoesNotExist:
        raise Http404("Invitation URL is not valid")
    if request.user.is_authenticated:
        messages.add_message(
            request, messages.ERROR, "You are signed in. Log out first."
        )
        return redirect("index")
    if not inv.is_valid():
        messages.add_message(request, messages.ERROR, "Invitation has expired.")
        return redirect("index")
    if request.method == "GET":
        form = UserCreationForm()
    elif request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            auth_login(request, user)
            inv.accept(user)
            messages.add_message(request, messages.SUCCESS, "Welcome")
            return redirect(reverse("account"))
    else:
        return redirect(reverse("index"))
    return render(request, "signup.html", {"form": form})
