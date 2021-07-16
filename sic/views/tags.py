from django.http import HttpResponseForbidden, Http404
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login
from django.db.models import Value, BooleanField
from django.urls import reverse
from django.contrib import messages
from django.core.paginator import Paginator, InvalidPage
from django.contrib.auth.decorators import login_required
from django.utils.timezone import make_aware
from django.utils.http import urlencode
from ..models import Tag, Story, Taggregation
from ..forms import EditTagForm, EditTaggregationForm, OrderByForm
from . import form_errors_as_string
from datetime import datetime


def browse_tags(request, page_num=1):
    if "order_by" in request.GET:
        request.session["tag_order_by"] = request.GET["order_by"]
    if "ordering" in request.GET:
        request.session["tag_ordering"] = request.GET["ordering"]
    order_by = request.session.get("tag_order_by", "created")
    ordering = request.session.get("tag_ordering", "desc")
    order_by_field = ("-" if ordering == "desc" else "") + order_by

    if page_num == 1 and request.get_full_path() != reverse("browse_tags"):
        return redirect(reverse("browse_tags"))
    if order_by in ["name", "created"]:
        tags = Tag.objects.order_by(order_by_field, "name")
    elif order_by == "active":
        tags = sorted(
            Tag.objects.all(),
            key=lambda t: t.latest.created
            if t.latest
            else make_aware(datetime.fromtimestamp(0)),
            reverse=ordering == "desc",
        )
    else:
        tags = sorted(
            Tag.objects.all(),
            key=lambda t: t.stories.count(),
            reverse=ordering == "desc",
        )
    paginator = Paginator(tags, 250)
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
    order_by_form = OrderByForm(
        fields=browse_tags.ORDER_BY_FIELDS,
        initial={"order_by": order_by, "ordering": ordering},
    )
    return render(
        request,
        "browse_tags.html",
        {"tags": page, "order_by_form": order_by_form},
    )


browse_tags.ORDER_BY_FIELDS = ["name", "created", "active", "number of posts"]


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
            return redirect(
                reverse("login") + "?" + urlencode({"next": obj.get_absolute_url()})
            )
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


@login_required
def new_aggregation(request):
    if request.method == "POST":
        form = EditTaggregationForm(request.POST)
        if form.is_valid():
            subscribed = form.cleaned_data["subscribed"]
            new = Taggregation.objects.create(
                creator=request.user,
                name=form.cleaned_data["name"],
                description=form.cleaned_data["description"],
                discoverable=form.cleaned_data["discoverable"],
                private=form.cleaned_data["private"],
            )
            new.tags.set(form.cleaned_data["tags"])
            new.moderators.add(request.user)
            new.save()
            if subscribed:
                request.user.taggregation_subscriptions.add(new)
            return redirect(new)
        error = form_errors_as_string(form.errors)
        messages.add_message(request, messages.ERROR, f"Invalid form. Error: {error}")
    else:
        form = EditTaggregationForm()
    return render(
        request,
        "edit_aggregation.html",
        {
            "form": form,
        },
    )


@login_required
def edit_aggregation(request, taggregation_pk, slug=None):
    try:
        obj = Taggregation.objects.get(pk=taggregation_pk)
    except Taggregation.DoesNotExist:
        raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
    if slug != obj.slugify():
        return redirect(obj.get_absolute_url())
    if not obj.user_has_access(request.user):
        raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
    if not obj.user_can_modify(request.user):
        return HttpResponseForbidden()
    user = request.user
    subscribed = user.taggregation_subscriptions.filter(pk=taggregation_pk).exists()

    if request.method == "POST":
        form = EditTaggregationForm(request.POST)
        if form.is_valid():
            new_subscribed = form.cleaned_data["subscribed"]
            if subscribed != new_subscribed:
                if subscribed:
                    user.taggregation_subscriptions.remove(obj)
                    messages.add_message(
                        request, messages.SUCCESS, f"You have unsubscribed from {obj}."
                    )
                else:
                    user.taggregation_subscriptions.add(obj)
                    messages.add_message(
                        request, messages.SUCCESS, f"You have subscribed to {obj}."
                    )
            obj.name = form.cleaned_data["name"]
            obj.description = form.cleaned_data["description"]
            obj.discoverable = form.cleaned_data["discoverable"]
            obj.private = form.cleaned_data["private"]
            obj.tags.set(form.cleaned_data["tags"])
            obj.save()
            if "next" in request.GET:
                return redirect(request.GET["next"])
            return redirect(obj)
        error = form_errors_as_string(form.errors)
        messages.add_message(request, messages.ERROR, f"Invalid form. Error: {error}")
    else:
        form = EditTaggregationForm(
            initial={
                "name": obj.name,
                "description": obj.description,
                "discoverable": obj.discoverable,
                "private": obj.private,
                "subscribed": subscribed,
                "tags": obj.tags.all(),
            }
        )
    return render(
        request,
        "edit_aggregation.html",
        {
            "form": form,
            "agg": obj,
        },
    )


def public_aggregations(request, page_num=1):
    if "order_by" in request.GET:
        request.session["agg_order_by"] = request.GET["order_by"]
    if "ordering" in request.GET:
        request.session["agg_ordering"] = request.GET["ordering"]
    order_by = request.session.get("agg_order_by", "created")
    ordering = request.session.get("agg_ordering", "desc")
    order_by_field = ("-" if ordering == "desc" else "") + order_by

    if page_num == 1 and request.get_full_path() != reverse("public_aggregations"):
        return redirect(reverse("public_aggregations"))
    taggs = (
        Taggregation.objects.exclude(discoverable=False)
        .exclude(private=True)
        .order_by(order_by_field, "name")
    )
    paginator = Paginator(taggs, 250)
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
    order_by_form = OrderByForm(
        fields=public_aggregations.ORDER_BY_FIELDS,
        initial={"order_by": order_by, "ordering": ordering},
    )
    return render(
        request,
        "browse_aggs.html",
        {"aggs": page, "order_by_form": order_by_form},
    )


public_aggregations.ORDER_BY_FIELDS = ["name", "created"]
