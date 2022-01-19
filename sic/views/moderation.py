from datetime import datetime, time
from django.contrib.auth.decorators import login_required, permission_required
from django.db import transaction
from django.http import Http404, HttpResponse
from django.views.decorators.http import require_http_methods
from django.urls import reverse
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import render, redirect
from django.utils.timezone import make_aware
from django.apps import apps
from django import forms
from django.core.exceptions import ValidationError

config = apps.get_app_config("sic")
from sic.moderation import ModerationLogEntry
from sic.models import Story, Comment, User, Domain, Taggregation, Notification
from sic.views.utils import (
    form_errors_as_string,
    Paginator,
    InvalidPage,
    check_next_url,
)
from sic.forms import validate_user


class BanUserForm(forms.Form):
    username = forms.CharField(
        required=True, label="username", validators=[validate_user]
    )
    ban = forms.BooleanField(
        label="ban",
        required=False,
        initial=True,
    )
    reason = forms.CharField(
        required=True,
        label="reason",
        widget=forms.Textarea({"rows": 2, "cols": 15, "placeholder": ""}),
    )

    def clean_username(self):
        value = self.cleaned_data["username"]
        try:
            user = User.objects.get(username=value)
            if user.is_moderator or user.is_admin:
                raise ValidationError(f"User {value} is staff.")
            return user
        except User.DoesNotExist:
            raise ValidationError(f"User {value} not found.")


@require_http_methods(["GET"])
def log(request, page_num=1):
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
        "moderation/moderation_log.html",
        {
            "logs": page,
            "pages": paginator.get_elided_page_range(number=page_num),
        },
    )


@require_http_methods(["GET"])
def banned_domains(request):
    banned_domains = Domain.objects.filter(is_banned=True)
    return render(
        request,
        "moderation/banned_domains.html",
        {
            "banned_domains": banned_domains,
        },
    )


@login_required
def overview(request):
    if (not request.user.is_moderator) and (not request.user.is_admin):
        raise PermissionDenied("You are not a moderator.")
    ban_user_form = BanUserForm()
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
        elif "remove-post" in request.POST:
            pass
        elif "domain-ban" in request.POST:
            try:
                domain_obj, _ = Domain.objects.get_or_create(
                    pk=request.POST["domain-pk"]
                )
                domain_obj.is_banned = not domain_obj.is_banned
                domain_obj.save(update_fields=["is_banned"])
            except KeyError:
                messages.add_message(
                    request,
                    messages.ERROR,
                    "Invalid form: domain_pk was missing from POST data. Is this a bug?",
                )
    banned_domains = Domain.objects.filter(is_banned=True)
    removed_posts = Story.objects.filter(active=False)
    return render(
        request,
        "moderation/overview.html",
        {
            "ban_user_form": ban_user_form,
            "banned_domains": banned_domains,
            "removed_posts": removed_posts,
        },
    )


class EditStoryForm(forms.Form):
    active = forms.BooleanField(
        label="is active",
        required=False,
        initial=True,
    )
    reason = forms.CharField(
        required=True,
        label="reason",
        widget=forms.Textarea({"rows": 2, "cols": 15, "placeholder": ""}),
    )


class EditStoryPinForm(forms.Form):
    pinned = forms.DateField(
        label="pinned until",
        required=False,
        initial=None,
        widget=forms.DateInput(attrs={"type": "date"}),
    )


@login_required
@transaction.atomic
def story(request, story_pk: int, slug=None):
    if (not request.user.is_moderator) and (not request.user.is_admin):
        raise PermissionDenied("You are not a moderator.")
    try:
        story_obj = Story.objects.get(pk=story_pk)
    except Story.DoesNotExist:
        raise Http404("Story does not exist") from Story.DoesNotExist

    history_logs = ModerationLogEntry.objects.filter(
        object_id=story_pk,
        content_type_id=Story.content_type().id,
    ).order_by("action_time")
    reason = None
    last = history_logs.last()
    if last:
        reason = last.reason
    if request.method == "POST":
        form = EditStoryForm(request.POST)
        pinned_form = EditStoryPinForm(request.POST)
        if "set-status" in request.POST:
            if form.is_valid():
                changed_status = form.cleaned_data["active"] != story_obj.active
                if changed_status:
                    story_obj.active = form.cleaned_data["active"]
                    story_obj.save(update_fields=["active"])
                if changed_status or form.cleaned_data["reason"].strip() != reason:
                    reason = form.cleaned_data["reason"].strip()
                    log_entry = ModerationLogEntry.changed_story_status(
                        story_obj,
                        request.user,
                        "Set active" if story_obj.active else "Set inactive",
                        reason,
                    )
                    messages.add_message(
                        request, messages.SUCCESS, f"{log_entry.action} {story_obj}"
                    )
                return redirect(reverse("moderation_story", args=[story_pk]))
            error = form_errors_as_string(form.errors)
            messages.add_message(
                request, messages.ERROR, f"Invalid form. Error: {error}"
            )
        elif (
            "set-pinned" in request.POST
            or "set-pinned-indefinitely" in request.POST
            or "set-pinned-unpin" in request.POST
        ):
            if pinned_form.is_valid():
                if "set-pinned-indefinitely" in request.POST:
                    pinned_form.cleaned_data["pinned"] = make_aware(
                        datetime.fromtimestamp(0)
                    )
                elif "set-pinned-unpin" in request.POST:
                    pinned_form.cleaned_data["pinned"] = None
                else:
                    pinned_form.cleaned_data["pinned"] = make_aware(
                        datetime.combine(pinned_form.cleaned_data["pinned"], time())
                    )
                changed_status = pinned_form.cleaned_data["pinned"] != story_obj.pinned
                if changed_status:
                    story_obj.pinned = pinned_form.cleaned_data["pinned"]
                    story_obj.save(update_fields=["pinned"])
                if changed_status:
                    log_entry = ModerationLogEntry.changed_story_status(
                        story_obj,
                        request.user,
                        (
                            "Pinned "
                            if story_obj.pinned.timestamp() == 0
                            else f"Pinned until {story_obj.pinned}"
                        )
                        if story_obj.pinned
                        else "Unpinned",
                        "",
                    )
                    messages.add_message(
                        request, messages.SUCCESS, f"{log_entry.action} {story_obj}"
                    )
                return redirect(reverse("moderation_story", args=[story_pk]))
            error = form_errors_as_string(pinned_form.errors)
            messages.add_message(
                request, messages.ERROR, f"Invalid form. Error: {error}"
            )
    else:
        form = EditStoryForm(initial={"active": story_obj.active, "reason": reason})
        pinned_form = EditStoryPinForm(
            initial={"pinned": story_obj.pinned if story_obj.pinned else None}
        )
    return render(
        request,
        "moderation/story.html",
        {
            "story": story_obj,
            "history_logs": history_logs,
            "form": form,
            "pinned_form": pinned_form,
        },
    )
