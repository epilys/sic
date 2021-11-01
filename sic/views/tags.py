from datetime import datetime
import random
import re
from django.db import transaction, connection, IntegrityError
from django.db.models.functions import Lower
from django.http import HttpResponse, Http404
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_http_methods
from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.utils.timezone import make_aware
from django.utils.http import urlencode
from django.views.decorators.cache import cache_page
from django.core.cache import cache
from django.views.decorators.clickjacking import xframe_options_exempt
from django.apps import apps

config = apps.get_app_config("sic")

from sic.models import Tag, Taggregation, TaggregationHasTag
from sic.forms import (
    NewTagForm,
    EditTagForm,
    EditTaggregationForm,
    OrderByForm,
    EditTaggregationHasTagForm,
    DeleteTaggregationHasTagForm,
)
from sic.views.utils import (
    form_errors_as_string,
    Paginator,
    InvalidPage,
    check_next_url,
)
from sic.moderation import ModerationLogEntry


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
    if order_by == "name":
        tags = Tag.objects.order_by(
            Lower("name").asc() if ordering == "asc" else Lower("name").desc()
        )
    elif order_by == "created":
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
            key=lambda t: t.stories_count(),
            reverse=ordering == "desc",
        )
    paginator = Paginator(tags, 250)
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        # page_num is bigger than the actual number of pages
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
        "tags/browse_tags.html",
        {
            "tags": page,
            "order_by_form": order_by_form,
            "pages": paginator.get_elided_page_range(number=page_num),
        },
    )


browse_tags.ORDER_BY_FIELDS = ["name", "created", "active", "number of posts"]

SVG_FONT_SIZE_PT: int = 12.0
SVG_STYLE = f"""1999/xlink">
<style>
div {{
font-size: {SVG_FONT_SIZE_PT-4}pt;
  border: 1px solid #0000005e;
  border-radius: 5px;
  color: #555;
  padding: 0px 0.4em 1px 0.4em;
  text-decoration: none;
  vertical-align: middle;

  --aa-brightness: ((var(--red) * 299) + (var(--green) * 587) + (var(--blue) * 114)) / 1000;
  --aa-color: calc((var(--aa-brightness) - 128) * -1000);
  background: rgb(var(--red), var(--green), var(--blue));
  color: rgb(var(--aa-color), var(--aa-color), var(--aa-color));
  width: max-content;
}}
  </style>"""


SVG_TAG_PATTERN = re.compile(
    r"""(?P<header><title>(?P<id>\d+)</title>.*?)<text [^>]*?x="(?P<x>[^"]*?)" y="(?P<y>[^"]*?)"[^>]*?>(?P<tag>[^<]*?)</text>""",
    re.MULTILINE | re.DOTALL,
)


@require_http_methods(["GET"])
@cache_page(60 * 60 * 12)
@xframe_options_exempt
def tag_graph_svg(request):
    import graphviz

    tag_pks = request.GET.getlist("tags")
    if tag_pks is None or len(tag_pks) == 0:
        tags = Tag.objects.all()
    else:
        tags = Tag.objects.filter(pk__in=tag_pks)

    dot = graphviz.Digraph(
        comment="tags",
        format="svg",
        node_attr={
            "shape": "none",
            "fontsize": str(SVG_FONT_SIZE_PT),
            "target": "_parent",
        },
    )
    dot.attr(size="18,5")
    for t in tags:
        dot.node(str(t.id), label=t.name, href=t.get_absolute_url())
    for t in tags:
        for p in t.parents.all():
            if p not in tags:
                continue
            dot.edge(str(p.id), str(t.id))
    try:
        dot = dot.unflatten(stagger=3, chain=5, fanout=True)
    except:
        pass

    def find_graph_dimensions(svg):
        try:
            scale = re.search(r"""<g.+?transform="scale.([^ ]*\s*[^)]*)""", svg)
            try:
                scale = float(scale[1].split()[0])
            except:
                scale = 1.0
            polygon = re.search(
                r"""<polygon.*?points="([^ ]* [^ ]* [^ ]* [^ ]*)""", svg
            )
            points = tuple(
                map(
                    lambda pair: tuple(map(lambda num: float(num), pair.split(","))),
                    polygon[1].split(),
                )
            )
            A, B, C, D = points
            height = (A[1] - B[1]) * scale
            width = (C[0] - B[0]) * scale
            return width, height
        except Exception as exc:
            wh = re.search(r"""svg width="(\d*)pt"\s*height="(\d*)pt"\s*""", svg)
            if not wh:
                return 1500.0, 600.0
            return wh[1], wh[2]

    try:
        import subprocess
        from subprocess import PIPE, Popen

        ccomps = Popen(["ccomps", "-x"], stdout=PIPE, stdin=PIPE)
        ccomps.stdin.write(dot.source.encode("utf-8"))
        ccomps.stdin.close()
        svg = subprocess.check_output(
            "dot | gvpack -array1 -n|neato -n2 -Tsvg", stdin=ccomps.stdout, shell=True
        ).decode("utf-8")
        width, height = find_graph_dimensions(svg)
        svg = re.sub(
            r"""svg width="(\d*)pt"\s*height="(\d*)pt"\s*viewBox="[^"]*"\s""",
            lambda matchobj: f"""svg width="{int(width)}pt" height="{int(height)}pt" viewBox="0.00 0.00 {int(width)} {int(height)}" """,
            svg,
            count=1,
        )
    except:
        svg = dot.pipe().decode("utf-8")
        width, height = find_graph_dimensions(svg)
        svg = re.sub(
            r"""svg width="(\d*)pt"\s*height="(\d*)pt"\s*viewBox="[^"]*"\s""",
            lambda matchobj: f"""svg width="{int(width)}pt" height="{int(height)}pt" viewBox="0.00 0.00 {int(width)} {int(height)}" """,
            svg,
            count=1,
        )

    svg = svg.replace('1999/xlink">', SVG_STYLE)
    tags = {t.pk: t for t in tags}

    def node_repl(matchobj):
        x = float(matchobj["x"])
        y = float(matchobj["y"])
        tag_name = matchobj["tag"]
        tag = tags[int(matchobj["id"])]
        width = (SVG_FONT_SIZE_PT - 4) * len(tag_name) * 0.77 + 20
        height = SVG_FONT_SIZE_PT * 2 * 1.33
        x -= width / 2 - 5
        y -= height / 4
        return f"""{matchobj['header']}<foreignObject x="{x}" y="{y}" width="{width}" height="{height}">
    <div xmlns="http://www.w3.org/1999/xhtml" style="{tag.color_vars_css()}">{tag_name}</div>
    </foreignObject>"""

    svg = re.sub(SVG_TAG_PATTERN, node_repl, svg)
    return HttpResponse(svg, content_type="image/svg+xml")


def taggregation(request, taggregation_pk, slug=None):
    try:
        obj = Taggregation.objects.get(pk=taggregation_pk)
    except Taggregation.DoesNotExist:
        raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
    if slug != obj.slugify:
        return redirect(obj.get_absolute_url())
    if not obj.user_has_access(request.user):
        if request.user.is_authenticated:
            raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
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
        "tags/taggregation.html",
        {
            "taggregation": obj,
            "user_can_modify": obj.user_can_modify(request.user),
            "subscribed": subscribed,
        },
    )


@login_required
@transaction.atomic
def copy_taggregation(request, taggregation_pk):
    user = request.user
    try:
        obj = Taggregation.objects.get(pk=taggregation_pk)
    except Taggregation.DoesNotExist:
        raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
    if not obj.user_has_access(user):
        raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
    new = Taggregation.objects.create(
        creator=user,
        name=f"{obj.name} copy",
        description=obj.description,
    )
    for has in obj.taggregationhastag_set.all():
        has.pk = None
        has.save()
        new.taggregationhastag_set.add(has)
    new.moderators.add(user)
    new.save()
    user.taggregation_subscriptions.add(new)
    messages.add_message(
        request, messages.SUCCESS, f"You have created and been subscribed to {new}."
    )
    return redirect(new)


@login_required
@transaction.atomic
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
    if "next" in request.GET and check_next_url(request.GET["next"]):
        return redirect(request.GET["next"])
    return redirect(reverse("account"))


@login_required
@permission_required("sic.change_tag", raise_exception=True)
@transaction.atomic
def edit_tag(request, tag_pk, slug=None):
    try:
        tag = Tag.objects.get(pk=tag_pk)
    except Tag.DoesNotExist:
        raise Http404("Tag does not exist") from Tag.DoesNotExist
    if slug != tag.slugify:
        return redirect(tag.get_absolute_url())
    if not request.user.has_perm("sic.change_tag", tag):
        raise PermissionDenied("You don't have permissions to change this tag.")
    if request.method == "POST":
        form = EditTagForm(request.POST)
        if form.is_valid():
            name_before = tag.name
            parents_before = list(tag.parents.all())

            err = None
            try:
                with transaction.atomic():
                    tag.parents.set(form.cleaned_data["parents"])
            except IntegrityError as exc:
                err = exc
                with connection.cursor() as cursor:
                    path_strs = []
                    for p in form.cleaned_data["parents"]:
                        cursor.execute(
                            f"SELECT already_visited FROM cycle_check_view WHERE last_visited = {p.pk} AND already_visited LIKE '%{tag.pk}%';",
                            [],
                        )
                        path = cursor.fetchone()
                        if path:
                            path = path[0]
                            if isinstance(path, str):
                                path = [p.pk] + list(map(int, path.split(","))) + [p.pk]
                            else:
                                path = [p.pk, path, p.pk]
                            path_strs.append(
                                "‘"
                                + "’ → ‘".join(
                                    map(lambda pk: Tag.objects.get(pk=pk).name, path)
                                )
                                + "’"
                            )
                form.add_error("parents", f"{exc} {','.join(path_strs)}")

            if err is None:
                tag.name = form.cleaned_data["name"]
                tag.hex_color = form.cleaned_data["hex_color"]

                if name_before != tag.name:
                    ModerationLogEntry.edit_tag_name(
                        name_before, tag, request.user, form.cleaned_data["reason"]
                    )
                if parents_before != list(form.cleaned_data["parents"]):
                    ModerationLogEntry.edit_tag_parents(
                        parents_before, tag, request.user, form.cleaned_data["reason"]
                    )

                tag.save()
                if "next" in request.GET and check_next_url(request.GET["next"]):
                    return redirect(request.GET["next"])
                return redirect(reverse("browse_tags"))
        error = form_errors_as_string(form.errors)
        messages.add_message(request, messages.ERROR, f"Invalid form. Error: {error}")
    else:
        form = EditTagForm(
            initial={
                "pk": tag,
                "name": tag.name,
                "hex_color": tag.hex_color,
                "parents": tag.parents.all(),
            }
        )
    # colors = list(gen_html(mix=[198, 31, 31]))
    colors = list(gen_html())
    form.fields["parents"].queryset = Tag.objects.exclude(pk=tag_pk)
    return render(
        request,
        "tags/edit_tag.html",
        {
            "tag": tag,
            "form": form,
            "colors": colors,
            "parents": {p.name: p.hex_color for p in form.fields["parents"].queryset},
        },
    )


@login_required
@permission_required("sic.add_tag", raise_exception=True)
@transaction.atomic
def add_tag(request):
    if not request.user.has_perm("sic.add_tag"):
        raise PermissionDenied("You don't have permissions to add tags.")
    colors = list(gen_html())
    if request.method == "POST":
        form = NewTagForm(request.POST)
        if form.is_valid():
            new = Tag.objects.create(
                name=form.cleaned_data["name"],
                hex_color=form.cleaned_data["hex_color"],
            )
            new.parents.set(form.cleaned_data["parents"])
            new.save()
            ModerationLogEntry.create_tag(new, request.user)
            messages.add_message(
                request, messages.SUCCESS, f"You have created a tag: {new.name}."
            )
            if "next" in request.GET and check_next_url(request.GET["next"]):
                return redirect(request.GET["next"])
            return redirect(reverse("browse_tags"))
        error = form_errors_as_string(form.errors)
        messages.add_message(request, messages.ERROR, f"Invalid form. Error: {error}")
    else:
        form = NewTagForm(initial={"hex_color": colors[0]})
    return render(
        request,
        "tags/edit_tag.html",
        {
            "form": form,
            "colors": colors,
            "parents": {p.name: p.hex_color for p in form.fields["parents"].queryset},
        },
    )


@login_required
@transaction.atomic
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
        "tags/edit_aggregation.html",
        {
            "form": form,
        },
    )


@login_required
@transaction.atomic
def edit_aggregation(request, taggregation_pk, slug=None):
    try:
        obj = Taggregation.objects.get(pk=taggregation_pk)
    except Taggregation.DoesNotExist:
        raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
    if slug != obj.slugify:
        return redirect(obj.get_absolute_url())
    if not obj.user_has_access(request.user):
        raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
    if not obj.user_can_modify(request.user):
        raise PermissionDenied("You don't have permissions to edit this aggregation.")
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
            obj.save()
            if "next" in request.GET and check_next_url(request.GET["next"]):
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
        "tags/edit_aggregation.html",
        {
            "form": form,
            "agg": obj,
        },
    )


@login_required
@transaction.atomic
def edit_aggregation_filter(request, taggregation_pk, slug, taggregationhastag_id):
    try:
        obj = Taggregation.objects.get(pk=taggregation_pk)
    except Taggregation.DoesNotExist:
        raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
    if not obj.user_has_access(request.user):
        raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
    if not obj.user_can_modify(request.user):
        raise PermissionDenied("You don't have permissions to edit this aggregation.")
    if slug != obj.slugify:
        return redirect(
            reverse(
                "edit_aggregation_filter",
                args=[taggregation_pk, obj.slugify, taggregationhastag_id],
            )
        )
    try:
        has = TaggregationHasTag.objects.get(
            taggregation__pk=taggregation_pk, id=taggregationhastag_id
        )
    except TaggregationHasTag.DoesNotExist:
        raise Http404(
            "Taggregation filter does not exist"
        ) from TaggregationHasTag.DoesNotExist
    user = request.user

    if request.method == "POST":
        form = EditTaggregationHasTagForm(request.POST)
        if form.is_valid():
            has.tag = form.cleaned_data["tag"]
            has.depth = form.cleaned_data["depth"]
            has.exclude_filters.set(form.cleaned_data["exclude_filters"])
            has.save(update_fields=["tag", "depth"])
            messages.add_message(request, messages.SUCCESS, "Filter edited succesfuly.")
            return redirect(obj)
        error = form_errors_as_string(form.errors)
        messages.add_message(request, messages.ERROR, f"Invalid form. Error: {error}")
    else:
        form = EditTaggregationHasTagForm(
            initial={
                "tag": has.tag,
                "depth": has.depth,
                "exclude_filters": has.exclude_filters.all(),
            }
        )
    return render(
        request,
        "tags/edit_filter.html",
        {
            "form": form,
            "agg": obj,
            "has": has,
            "delete_form": DeleteTaggregationHasTagForm(initial={"pk": has}),
        },
    )


@login_required
@transaction.atomic
def new_aggregation_filter(request, taggregation_pk, slug):
    try:
        obj = Taggregation.objects.get(pk=taggregation_pk)
    except Taggregation.DoesNotExist:
        raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
    if not obj.user_has_access(request.user):
        raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
    if not obj.user_can_modify(request.user):
        raise PermissionDenied("You don't have permissions to edit this aggregation.")
    if slug != obj.slugify:
        return redirect(
            reverse("new_aggregation_filter", args=[taggregation_pk, obj.slugify])
        )
    user = request.user

    if request.method == "POST":
        form = EditTaggregationHasTagForm(request.POST)
        if form.is_valid():
            has = TaggregationHasTag(
                taggregation=obj,
                tag=form.cleaned_data["tag"],
                depth=form.cleaned_data["depth"],
            )
            has.save()
            has.exclude_filters.set(form.cleaned_data["exclude_filters"])
            messages.add_message(
                request, messages.SUCCESS, "Filter created succesfuly."
            )
            return redirect(obj)
        error = form_errors_as_string(form.errors)
        messages.add_message(request, messages.ERROR, f"Invalid form. Error: {error}")
    else:
        form = EditTaggregationHasTagForm()
    return render(
        request,
        "tags/edit_filter.html",
        {
            "form": form,
            "agg": obj,
            "has": None,
        },
    )


@login_required
@transaction.atomic
@require_http_methods(["POST"])
def delete_aggregation_filter(request, taggregation_pk):
    try:
        obj = Taggregation.objects.get(pk=taggregation_pk)
    except Taggregation.DoesNotExist:
        raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
    if not obj.user_has_access(request.user):
        raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
    if not obj.user_can_modify(request.user):
        raise PermissionDenied("You don't have permissions to edit this aggregation.")

    form = DeleteTaggregationHasTagForm(request.POST)
    if form.is_valid():
        has = form.cleaned_data["pk"]
        has.delete()
    return redirect(obj)


def browse_aggs(request, view_name, aggregations, page_num=1):
    if "order_by" in request.GET:
        request.session["agg_order_by"] = request.GET["order_by"]
    if "ordering" in request.GET:
        request.session["agg_ordering"] = request.GET["ordering"]
    order_by = request.session.get("agg_order_by", "created")
    ordering = request.session.get("agg_ordering", "desc")
    order_by_field = ("-" if ordering == "desc" else "") + order_by

    if page_num == 1 and request.get_full_path() != reverse(view_name):
        return redirect(reverse(view_name))
    taggs = aggregations.order_by(order_by_field, "name")
    paginator = Paginator(taggs, 30)
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        # page_num is bigger than the actual number of pages
        return redirect(
            reverse(
                f"{view_name}_page",
                kwargs={"page_num": paginator.num_pages},
            )
        )
    order_by_form = OrderByForm(
        fields=browse_aggs.ORDER_BY_FIELDS,
        initial={"order_by": order_by, "ordering": ordering},
    )
    return render(
        request,
        "tags/browse_aggs.html",
        {
            "aggs": page,
            "order_by_form": order_by_form,
            "view_name": view_name,
            "view_name_page": f"{view_name}_page",
            "pages": paginator.get_elided_page_range(number=page_num),
        },
    )


browse_aggs.ORDER_BY_FIELDS = ["name", "created"]


def personal_aggregations(request, page_num=1):
    if not request.user.is_authenticated:
        return public_aggregations(request, page_num)
    aggregations = request.user.taggregation_subscriptions.all()
    if not aggregations.exists():
        return public_aggregations(request, page_num)
    return browse_aggs(request, "personal_aggregations", aggregations, page_num)


def public_aggregations(request, page_num=1):
    aggregations = Taggregation.objects.exclude(discoverable=False).exclude(
        private=True
    )
    return browse_aggs(request, "public_aggregations", aggregations, page_num)


def default_aggregations(request, page_num=1):
    aggregations = (
        Taggregation.objects.exclude(discoverable=False)
        .exclude(private=True)
        .filter(default=True)
    )
    return browse_aggs(request, "default_aggregations", aggregations, page_num)


# HSV values in [0..1[
# returns [r, g, b] values from 0 to 255
def hsv_to_rgb(h, s, v):
    h_i = int(h * 6)
    f = h * 6 - h_i
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    if h_i == 0:
        r, g, b = v, t, p
    if h_i == 1:
        r, g, b = q, v, p
    if h_i == 2:
        r, g, b = p, v, t
    if h_i == 3:
        r, g, b = p, q, v
    if h_i == 4:
        r, g, b = t, p, v
    if h_i == 5:
        r, g, b = v, p, q
    return [int(r * 256), int(g * 256), int(b * 256)]


def gen_html(mix=None):
    # use golden ratio
    golden_ratio_conjugate = 0.618033988749895
    for _ in range(0, 50):
        h = random.random()
        h += golden_ratio_conjugate
        h %= 1
        [r, g, b] = hsv_to_rgb(h, 0.5, 0.95)
        if mix:
            r = int((r + mix[0]) / 2)
            g = int((g + mix[1]) / 2)
            b = int((b + mix[2]) / 2)
        yield "#%02x%02x%02x" % (r, g, b)


def view_tag(request, tag_pk, slug=None, page_num=1):
    try:
        obj = Tag.objects.get(pk=tag_pk)
    except Tag.DoesNotExist:
        raise Http404("Tag does not exist") from Tag.DoesNotExist
    if "order_by" in request.GET:
        request.session["tag_order_by"] = request.GET["order_by"]
    if "ordering" in request.GET:
        request.session["tag_ordering"] = request.GET["ordering"]
    if page_num == 1 and request.get_full_path() != reverse(
        "view_tag", kwargs={"tag_pk": tag_pk, "slug": slug}
    ):
        return redirect(reverse("view_tag", kwargs={"tag_pk": tag_pk, "slug": slug}))
    if slug != obj.slugify:
        return redirect(
            reverse(
                "view_tag_page",
                kwargs={"tag_pk": tag_pk, "slug": obj.slugify, "page_num": page_num},
            )
        )
    order_by = request.session.get("tag_order_by", "created")
    ordering = request.session.get("tag_ordering", "desc")

    if order_by == "created":
        stories = list(obj.get_stories())
        stories = sorted(
            stories,
            key=lambda s: s.created,
            reverse=ordering == "desc",
        )
    elif order_by == "active":
        stories = list(obj.get_stories())
        stories = sorted(
            stories,
            key=lambda s: s.active_comments.latest("created").created
            if s.active_comments.exists()
            else make_aware(datetime.fromtimestamp(0)),
            reverse=ordering == "desc",
        )

    elif order_by == "number of comments":
        stories = list(obj.get_stories())
        stories = sorted(
            stories,
            key=lambda s: s.active_comments.count(),
            reverse=ordering == "desc",
        )
    else:
        stories = list(obj.get_stories())

    paginator = Paginator(stories, config.STORIES_PER_PAGE)
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        # page_num is bigger than the actual number of pages
        return redirect(
            reverse(
                "view_tag_page",
                kwargs={
                    "tag_pk": tag_pk,
                    "slug": obj.slugify,
                    "page_num": paginator.num_pages,
                },
            )
        )
    order_by_form = OrderByForm(
        fields=view_tag.ORDER_BY_FIELDS,
        initial={"order_by": order_by, "ordering": ordering},
    )
    return render(
        request,
        "posts/all_stories.html",
        {
            "stories": page,
            "order_by_form": order_by_form,
            "tag": obj,
            "pages": paginator.get_elided_page_range(number=page_num),
        },
    )


view_tag.ORDER_BY_FIELDS = ["created", "active", "number of comments"]
