__all__ = ["stories", "tags", "account", "utils", "stats"]
from datetime import datetime
import hashlib
from django.http import (
    Http404,
    HttpResponse,
    HttpResponseBadRequest,
)
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login as auth_login
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.views.decorators.http import require_http_methods
from django.utils.timezone import make_aware
from django.db.models import Max
from django.utils.http import urlencode
from django.apps import apps

config = apps.get_app_config("sic")
from sic.models import Story, Comment, User, Domain, Taggregation, Notification
from sic.moderation import ModerationLogEntry
from sic.forms import (
    SubmitCommentForm,
    EditReplyForm,
    DeleteCommentForm,
    SubmitStoryForm,
    SearchCommentsForm,
    BanUserForm,
    OrderByForm,
)
from sic.views.utils import (
    form_errors_as_string,
    Paginator,
    InvalidPage,
    check_next_url,
)
from sic.markdown import comment_to_html
from sic.search import query_comments, query_stories


@login_required
def preview_comment(request):
    if "next" not in request.GET or not check_next_url(request.GET["next"]):
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
            return redirect(request.GET["next"] + "#" + comment.slugify)
        return redirect(request.GET["next"])
    except (Comment.DoesNotExist, KeyError):
        return redirect(request.GET["next"])


@login_required
def reply(request, comment_pk):
    user = request.user
    try:
        comment = Comment.objects.get(pk=comment_pk)
    except Comment.DoesNotExist:
        raise Http404("Comment does not exist") from Comment.DoesNotExist
    if request.method == "POST":
        form = SubmitCommentForm(request.POST)
        if not user.has_perm("sic.add_comment"):
            if user.banned_by_user is not None:
                messages.add_message(
                    request,
                    messages.ERROR,
                    "You are banned and not allowed to comment.",
                )
            else:
                messages.add_message(
                    request, messages.ERROR, "You are not allowed to comment."
                )
        elif form.is_valid():
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


def agg_index(request, taggregation_pk, slug, page_num=1):
    if page_num == 1 and request.get_full_path() != reverse(
        "agg_index", kwargs={"taggregation_pk": taggregation_pk, "slug": slug}
    ):
        return redirect(
            reverse(
                "agg_index", kwargs={"taggregation_pk": taggregation_pk, "slug": slug}
            )
        )
    try:
        agg = Taggregation.objects.get(pk=taggregation_pk)
    except Taggregation.DoesNotExist:
        raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
    if slug != agg.slugify:
        return redirect(agg.get_absolute_url())
    if not agg.user_has_access(request.user):
        if request.user.is_authenticated:
            raise Http404("Taggregation does not exist") from Taggregation.DoesNotExist
        return redirect(
            reverse("login")
            + "?"
            + urlencode(
                {
                    "next": reverse(
                        "agg_index_page",
                        kwargs={
                            "taggregation_pk": taggregation_pk,
                            "slug": slug,
                            "page_num": page_num,
                        },
                    )
                }
            )
        )
    stories = agg.get_stories()
    # https://docs.python.org/3/howto/sorting.html#sort-stability-and-complex-sorts
    all_stories = sorted(
        stories,
        key=lambda s: s.title,
        reverse=True,
    )
    all_stories = sorted(
        all_stories,
        key=lambda s: s.created,
    )
    all_stories = sorted(
        all_stories,
        key=lambda s: s.hotness["score"],
        reverse=True,
    )
    paginator = Paginator(all_stories, config.STORIES_PER_PAGE)
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        # page_num is bigger than the actual number of pages
        return redirect(
            reverse(
                "agg_index_page",
                kwargs={
                    "taggregation_pk": taggregation_pk,
                    "slug": slug,
                    "page_num": paginator.num_pages,
                },
            )
        )
    return render(
        request,
        "index.html",
        {
            "stories": page,
            "has_subscriptions": True,
            "aggregation": agg,
            "pages": paginator.get_elided_page_range(number=page_num),
        },
    )


def index(request, page_num=1):
    if page_num == 1 and request.get_full_path() != reverse("index"):
        # Redirect to '/' to avoid having both '/' and '/page/1' as valid urls.
        return redirect(reverse("index"))
    stories = None
    has_subscriptions = False
    # Figure out what to show in the index
    # If user is authenticated AND has subscribed aggregations, show the set union of them
    # otherwise show every story.
    if request.user.is_authenticated:
        frontpage = request.user.frontpage()
        has_subscriptions = frontpage["taggregations"] is not None
    else:
        frontpage = Taggregation.default_frontpage()
    stories = frontpage["stories"]
    taggregations = frontpage["taggregations"]
    # https://docs.python.org/3/howto/sorting.html#sort-stability-and-complex-sorts
    all_stories = sorted(
        stories,
        key=lambda s: s.title,
        reverse=True,
    )
    all_stories = sorted(
        all_stories,
        key=lambda s: s.created,
    )
    all_stories = sorted(
        all_stories,
        key=lambda s: s.hotness["score"],
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
            "pages": paginator.get_elided_page_range(number=page_num),
        },
    )


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
                if "comment_preview" in request.session:
                    request.session["comment_preview"] = {}
                return redirect(comment_obj)
        error = form_errors_as_string(form.errors)
        messages.add_message(request, messages.ERROR, f"Invalid form. Error: {error}")
    else:
        form = EditReplyForm(
            initial={
                "text": comment_obj.text,
            },
        )
    return render(
        request,
        "posts/edit_comment.html",
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
                if "comment_preview" in request.session:
                    request.session["comment_preview"] = {}
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
            "posts/edit_comment.html",
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
    if "next" in request.GET and check_next_url(request.GET["next"]):
        return redirect(request.GET["next"])
    return redirect(reverse("index"))


def recent_comments(request, page_num=1):
    if page_num == 1 and request.get_full_path() != reverse("recent_comments"):
        # Redirect to '/' to avoid having both '/' and '/page/1' as valid urls.
        return redirect(reverse("recent_comments"))
    comments = (
        Comment.objects.filter(deleted=False)
        .prefetch_related("user")
        .order_by("-created")
    )
    paginator = Paginator(comments[:40], config.STORIES_PER_PAGE)
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        # page_num is bigger than the actual number of pages
        return redirect(
            reverse("recent_comments_page", kwargs={"page_num": paginator.num_pages})
        )
    return render(
        request,
        "posts/recent_comments.html",
        {
            "comments": page,
            "pages": paginator.get_elided_page_range(number=page_num),
        },
    )


def invitation_tree(request):
    root_user = User.objects.earliest("created")

    return render(
        request,
        "about/about_invitation_tree.html",
        {
            "root_user": root_user,
            "depth": 0,
            "max_depth": 64,
        },
    )


@require_http_methods(["GET"])
def comment_source(request, story_pk, slug, comment_pk=None):
    try:
        story_obj = Story.objects.get(pk=story_pk)
    except Story.DoesNotExist:
        raise Http404("Story does not exist") from Story.DoesNotExist
    if comment_pk is None:
        return HttpResponse(
            story_obj.description, content_type="text/plain; charset=utf-8"
        )
    try:
        comment_obj = Comment.objects.get(pk=comment_pk)
    except Comment.DoesNotExist:
        raise Http404("Comment does not exist") from Comment.DoesNotExist
    return HttpResponse(comment_obj.text, content_type="text/plain; charset=utf-8")


@require_http_methods(["GET"])
def search(request):
    count = None
    comments = None
    stories = None
    if "text" in request.GET:
        form = SearchCommentsForm(request.GET)
        if form.is_valid():
            if form.cleaned_data["search_in"] in ["comments", "both"]:
                comments = query_comments(form.cleaned_data["text"])
                count = len(comments)
            if form.cleaned_data["search_in"] in ["stories", "both"]:
                stories = query_stories(form.cleaned_data["text"])
                if count is None:
                    count = 0
                count += len(stories)
    else:
        form = SearchCommentsForm()
    return render(
        request,
        "posts/search.html",
        {"form": form, "comments": comments, "stories": stories, "count": count},
    )


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
        "moderation/moderation_log.html",
        {
            "logs": page,
            "pages": paginator.get_elided_page_range(number=page_num),
        },
    )


@login_required
def moderation(request):
    if (not request.user.is_moderator) and (not request.user.is_admin):
        raise PermissionDenied("You are not a moderator.")
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
    return render(
        request, "moderation/moderation.html", {"ban_user_form": ban_user_form}
    )


def domain(request, slug, page_num=1):
    try:
        domain_obj = Domain.objects.get(url=Domain.deslugify(slug))
    except Domain.DoesNotExist:
        raise Http404("Domain does not exist") from Domain.DoesNotExist
    if "order_by" in request.GET:
        request.session["domain_order_by"] = request.GET["order_by"]
    if "ordering" in request.GET:
        request.session["domain_ordering"] = request.GET["ordering"]
    if page_num == 1 and request.get_full_path() != reverse("domain", args=[slug]):
        return redirect(reverse("domain", args=[slug]))
    order_by = request.session.get("domain_order_by", "created")
    if order_by not in domain.ORDER_BY_FIELDS:
        order_by = domain.ORDER_BY_FIELDS[0]
    ordering = request.session.get("domain_ordering", "desc")
    order_by_field = ("-" if ordering == "desc" else "") + order_by
    stories = (
        Story.objects.filter(active=True, domain=domain_obj)
        .prefetch_related("tags", "user", "comments")
        .order_by(order_by_field)
    )
    paginator = Paginator(stories, config.STORIES_PER_PAGE)
    try:
        page = paginator.page(page_num)
    except InvalidPage:
        # page_num is bigger than the actual number of pages
        return redirect(
            reverse(
                "domain_page",
                args=[slug],
                kwargs={
                    "page_num": paginator.num_pages,
                },
            )
        )

    order_by_form = OrderByForm(
        fields=domain.ORDER_BY_FIELDS,
        initial={"order_by": order_by, "ordering": ordering},
    )
    return render(
        request,
        "posts/all_stories.html",
        {
            "stories": page,
            "order_by_form": order_by_form,
            "domain": domain_obj,
            "pages": paginator.get_elided_page_range(number=page_num),
        },
    )


domain.ORDER_BY_FIELDS = ["created", "title"]
