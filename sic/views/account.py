from django.http import HttpResponseForbidden, Http404
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login
from django.db.models import Value, BooleanField
from django.urls import reverse
from django.contrib import messages
from django.core.paginator import Paginator, InvalidPage
from django.contrib.auth.decorators import login_required
from wand.image import Image
from ..models import User, Invitation, Story, StoryBookmark
from ..forms import (
    GenerateInviteForm,
    EditProfileForm,
    EditAvatarForm,
    EditAccountSettings,
    SubmitReplyForm,
    UserCreationForm,
    AnnotationForm,
)
from ..apps import SicAppConfig as config
from . import form_errors_as_string, HttpResponseNotImplemented


def login(request):
    if request.method == "POST":
        username = request.POST["username"]
        password = request.POST["password"]
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            return redirect(reverse("index"))
        messages.add_message(request, messages.ERROR, "Could not login.")
    return render(request, "login.html")


@login_required
def view_account(request):
    user = request.user
    generate_invite_form = GenerateInviteForm()
    hats = None
    can_add_hats = user.has_perm("sic.add_hat")
    if can_add_hats:
        hats = user.hats.all()
    return render(
        request,
        "account.html",
        {
            "user": request.user,
            "generate_invite_form": generate_invite_form,
            "can_add_hats": can_add_hats,
            "hats": hats,
        },
    )


@login_required
def edit_profile(request):
    user = request.user
    if request.method == "POST":
        form = EditProfileForm(request.POST)
        if form.is_valid():
            request.user.homepage = form.cleaned_data["homepage"]
            request.user.git_repository = form.cleaned_data["git_repository"]
            request.user.about = form.cleaned_data["about"]
            request.user.save()
            return redirect(reverse("account"))
        error = form_errors_as_string(form.errors)
        messages.add_message(request, messages.ERROR, f"Invalid form. Error: {error}")
    else:
        initial = {
            "homepage": user.homepage,
            "git_repository": user.git_repository,
            "about": user.about,
        }
        form = EditProfileForm(initial=initial)
    return render(request, "edit_profile.html", {"user": request.user, "form": form})


@login_required
def edit_avatar(request):
    # Convert image to data:image/... in order to save avatars as strings in database

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
        if "delete-image" in request.POST:
            request.user.avatar = None
            request.user.save()
            return redirect(reverse("account"))
        form = EditAvatarForm(request.POST, request.FILES)
        if form.is_valid():
            img = form.cleaned_data["new_avatar"]
            print(img)
            avatar_title = form.cleaned_data["avatar_title"]
            if img:
                data_url = generate_image_thumbnail(img)
                request.user.avatar = data_url
            request.user.avatar_title = avatar_title if len(avatar_title) > 0 else None
            request.user.save()
            return redirect(reverse("account"))
        error = form_errors_as_string(form.errors)
        messages.add_message(request, messages.ERROR, f"Invalid form. Error: {error}")
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
            raise Http404("User does not exist") from User.DoesNotExist
    return render(request, "profile.html", {"user": user})


@login_required
def inbox(request):
    user = request.user
    inbox_messages = list(user.received_messages.all()) + list(user.sent_messages.all())
    return render(request, "inbox.html", {"messages": inbox_messages})


@login_required
def generate_invite(request, invite_pk=None):
    if invite_pk:
        try:
            inv = Invitation.objects.get(pk=invite_pk)
        except Invitation.DoesNotExist:
            raise Http404("Invitation URL is not valid") from Invitation.DoesNotExist
        if inv.inviter != request.user:
            return HttpResponseForbidden()
        if not inv.is_valid():
            messages.add_message(request, messages.ERROR, "Invitation has expired.")
        else:
            inv.send(request)
    elif request.method == "POST":
        user = request.user
        form = GenerateInviteForm(request.POST)
        if form.is_valid():
            address = form.cleaned_data["email"]
            inv, created = user.invited.get_or_create(inviter=user, address=address)
            if created:
                messages.add_message(
                    request,
                    messages.SUCCESS,
                    f"Successfully generated invitation to {address}.",
                )
                inv.send(request)
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
        raise Http404("User does not exist") from User.DoesNotExist
    story_obj = list(
        user.stories.filter(active=True)
        .annotate(is_story=Value("True", output_field=BooleanField()))
        .order_by("-created", "title")
    ) + list(
        user.comments.filter(deleted=False)
        .annotate(is_story=Value("False", output_field=BooleanField()))
        .order_by("-created")
    )
    story_obj = sorted(story_obj, key=lambda x: x.created, reverse=True)
    paginator = Paginator(story_obj, config.STORIES_PER_PAGE)
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        # page_num BooleanFieldis bigger than the actual number of pages
        return redirect(
            reverse(
                "profile_posts_page",
                args=[username],
                kwargs={"page_num": paginator.num_pages},
            )
        )
    return render(
        request,
        "profile_posts.html",
        {"posts": page, "reply_form": SubmitReplyForm(), "user": user},
    )


def accept_invite(request, invite_pk):
    try:
        inv = Invitation.objects.get(pk=invite_pk)
    except Invitation.DoesNotExist:
        raise Http404("Invitation URL is not valid") from Invitation.DoesNotExist
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


@login_required
def save_story(request, story_pk):
    if request.method == "GET":
        user = request.user
        try:
            story_obj = Story.objects.get(pk=story_pk)
        except Story.DoesNotExist:
            raise Http404("Story does not exist") from Story.DoesNotExist
        if user.saved_stories.filter(pk=story_obj.pk).exists():
            user.saved_stories.remove(story_obj)
        else:
            user.saved_stories.add(story_obj, through_defaults=None)
        print(StoryBookmark.objects.all())
    if "next" in request.GET:
        return redirect(request.GET["next"])
    return redirect(reverse("index"))


@login_required
def bookmarks(request, page_num=1):
    if page_num == 1 and request.get_full_path() != reverse("bookmarks"):
        return redirect(reverse("bookmarks"))
    user = request.user
    story_obj = list(
        user.saved_stories.through.objects.filter(story__active=True)
        .annotate(is_story=Value("True", output_field=BooleanField()))
        .select_related("story")
        .order_by("-created", "story__title")
    ) + list(
        user.saved_comments.through.objects.filter(comment__deleted=False)
        .annotate(is_story=Value("False", output_field=BooleanField()))
        .order_by("-created")
        .select_related("comment")
    )
    story_obj = sorted(story_obj, key=lambda x: x.created, reverse=True)
    paginator = Paginator(story_obj, config.STORIES_PER_PAGE)
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        # page_num BooleanFieldis bigger than the actual number of pages
        return redirect(
            reverse(
                "bookmarks_page",
                kwargs={"page_num": paginator.num_pages},
            )
        )
    return render(
        request,
        "bookmarks.html",
        {"bookmarks": page, "reply_form": SubmitReplyForm(), "user": user},
    )


@login_required
def edit_bookmark(request, bookmark_pk):
    """
        if request.method == "POST":
            annotation_form = AnnotationForm(request.POST)
            if annotation_form.is_valid():
                pk = request.POST["bookmark_pk"]
                print(pk)
        else:
            annotation_form = AnnotationForm()
    "annotation_form": annotation_form,
    """
    return HttpResponseNotImplemented("HTTP 501: Not implemented")


@login_required
def edit_settings(request):
    user = request.user
    if request.method == "POST":
        form = EditAccountSettings(request.POST)
        if form.is_valid():
            user.email_notifications = form.cleaned_data["email_notifications"]
            user.email_replies = form.cleaned_data["email_replies"]
            user.email_messages = form.cleaned_data["email_messages"]
            user.email_mentions = form.cleaned_data["email_mentions"]
            user.show_avatars = form.cleaned_data["show_avatars"]
            user.show_story_previews = form.cleaned_data["show_story_previews"]
            user.show_submitted_story_threads = form.cleaned_data[
                "show_submitted_story_threads"
            ]
            user.save()
            return redirect(reverse("account"))
        error = form_errors_as_string(form.errors)
        messages.add_message(request, messages.ERROR, f"Invalid form. Error: {error}")
    else:
        form = EditAccountSettings(initial=user._wrapped.__dict__)
    return render(request, "edit_settings.html", {"user": user, "form": form})


@login_required
def notifications(request):
    user = request.user
    actives = list(user.notifications.filter(active=True).order_by("-created"))
    rest = list(user.notifications.filter(active=False).order_by("-created"))
    user.notifications.filter(active=True).update(active=False)
    return render(
        request,
        "notifications.html",
        {"user": user, "active_notifications": actives, "rest_notifications": rest},
    )
