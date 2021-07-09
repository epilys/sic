from django.http import HttpResponseForbidden, Http404
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login
from django.db.models import Value, BooleanField
from django.urls import reverse
from django.contrib import messages
from django.core.paginator import Paginator, InvalidPage
from django.contrib.auth.decorators import login_required
from ..models import Tag, Story, Taggregation
from ..forms import EditTagForm
from . import form_errors_as_string


def browse_tags(request, page_num=1):
    if page_num == 1 and request.get_full_path() != reverse("browse_tags"):
        return redirect(reverse("browse_tags"))
    tags = Tag.objects.order_by("-created", "name")
    paginator = Paginator(tags, 10)
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        # page_num BooleanFieldis bigger than the actual number of pages
        return redirect(
            reverse(
                "browse_tags_page",
                kwargs={"page_num": paginator.num_pages},
            )
        )
    return render(
        request,
        "browse_tags.html",
        {"tags": page},
    )


def taggregation(request, taggregation_pk, slug=None):
    try:
        obj = Taggregation.objects.get(pk=taggregation_pk)
    except Taggregation.DoesNotExist:
        raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
    if slug != obj.slugify():
        return redirect(obj.get_absolute_url())
    if not obj.user_has_access(request.user):
        if request.user.is_authenticated:
            raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
        else:
            return redirect(reverse("login", kwargs={"next": obj.get_absolute_url()}))
    if request.user.is_authenticated:
        subscribed = request.user.taggregation_subscriptions.filter(
            pk=taggregation_pk
        ).exists()
    else:
        subscribed = False

    return render(
        request,
        "taggregation.html",
        {
            "taggregation": obj,
            "user_can_modify": obj.user_can_modify(request.user),
            "subscribed": subscribed,
        },
    )


@login_required
def taggregation_change_subscription(request, taggregation_pk):
    user = request.user
    try:
        obj = Taggregation.objects.get(pk=taggregation_pk)
    except Taggregation.DoesNotExist:
        raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
    if not obj.user_has_access(user):
        raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
    if user.taggregation_subscriptions.filter(pk=taggregation_pk).exists():
        user.taggregation_subscriptions.remove(obj)
        messages.add_message(
            request, messages.SUCCESS, f"You have unsubscribed from {obj}."
        )
    else:
        user.taggregation_subscriptions.add(obj)
        messages.add_message(
            request, messages.SUCCESS, f"You have subscribed to {obj}."
        )
    print(list(request.GET.items()))
    if "next" in request.GET:
        return redirect(request.GET["next"])
    return redirect(reverse("account"))


@login_required
def edit_tag(request, tag_pk, slug=None):
    try:
        tag = Tag.objects.get(pk=tag_pk)
    except Tag.DoesNotExist:
        raise Http404("Tag does not exist") from Tag.DoesNotExist
    if slug != tag.slugify():
        return redirect(tag.get_absolute_url())
    if not request.user.has_perm("sic.change_tag"):
        return HttpResponseForbidden()
    if request.method == "POST":
        form = EditTagForm(request.POST)
        if form.is_valid():
            tag.name = form.cleaned_data["name"]
            tag.hex_color = form.cleaned_data["hex_color"]
            tag.parents.set(form.cleaned_data["parents"])
            tag.save()
            if "next" in request.GET:
                return redirect(request.GET["next"])
            return redirect(reverse("browse_tags"))
        error = form_errors_as_string(form.errors)
        messages.add_message(request, messages.ERROR, f"Invalid form. Error: {error}")
    else:
        form = EditTagForm(
            initial={
                "name": tag.name,
                "hex_color": tag.hex_color,
                "parents": tag.parents.all(),
            }
        )
    return render(
        request,
        "edit_tag.html",
        {
            "tag": tag,
            "form": form,
        },
    )


@login_required
def add_tag(request):
    if not request.user.has_perm("sic.add_tag"):
        return HttpResponseForbidden()
    if request.method == "POST":
        form = EditTagForm(request.POST)
        if form.is_valid():
            new = Tag.objects.create(
                name=form.cleaned_data["name"],
                hex_color=form.cleaned_data["hex_color"],
            )
            new.parents.set(form.cleaned_data["parents"])
            new.save()
            if "next" in request.GET:
                return redirect(request.GET["next"])
            return redirect(reverse("browse_tags"))
        error = form_errors_as_string(form.errors)
        messages.add_message(request, messages.ERROR, f"Invalid form. Error: {error}")
    else:
        form = EditTagForm()
    return render(
        request,
        "edit_tag.html",
        {
            "form": form,
        },
    )
