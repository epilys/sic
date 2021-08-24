"""sic URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from django.views.generic import RedirectView
from django.views.generic.base import TemplateView
from django.shortcuts import render
from django.views.decorators.cache import cache_page

from sic import views
from sic.views import stories, account, tags, stats
from .auth import AuthenticationForm
from .feeds import LatestStoriesRss, LatestStoriesAtom, user_feeds_rss, user_feeds_atom
from .webfinger import webfinger
from sic.webmention import webmention_endpoint

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "formatting-help/",
        TemplateView.as_view(template_name="posts/markdown_help.html"),
        name="formatting_help",
    ),
    path(
        "about/", TemplateView.as_view(template_name="about/about.html"), name="about"
    ),
    path(
        "about/help/",
        TemplateView.as_view(template_name="about/help.html"),
        name="help",
    ),
    path(
        "about/purpose/",
        TemplateView.as_view(template_name="about/purpose.html"),
        name="purpose",
    ),
    path(
        "about/contact/",
        TemplateView.as_view(template_name="about/about_contact.html"),
        name="about_contact",
    ),
    path(
        "about/code-of-conduct/",
        TemplateView.as_view(template_name="about/coc.html"),
        name="code_of_conduct",
    ),
    path("about/invitation-tree/", views.invitation_tree, name="invitation_tree"),
    path(
        "about/privacy/",
        TemplateView.as_view(template_name="about/privacy.html"),
        name="about_privacy",
    ),
    path(
        "about/statistics/",
        TemplateView.as_view(template_name="about/statistics.html"),
        name="about_statistics",
    ),
    path(
        "about/statistics/svg/daily_posts/",
        stats.daily_posts_svg,
        name="daily_posts_svg",
    ),
    path(
        "about/statistics/svg/registrations/",
        stats.registrations_svg,
        name="registrations_svg",
    ),
    path(
        "about/statistics/svg/total-tag-graph/",
        stats.total_graph_svg,
        name="total_graph_svg",
    ),
    path(
        "about/statistics/svg/upvote-ratio-graph/",
        stats.upvote_ratio_svg,
        name="upvote_ratio_svg",
    ),
    path("moderation-log/", views.moderation_log, name="moderation_log"),
    path(
        "moderation-log/<int:page_num>/",
        views.moderation_log,
        name="moderation_log_page",
    ),
    path("moderation/", views.moderation, name="moderation"),
    path("", views.index, name="index"),
    path("page/<int:page_num>/", views.index, name="index_page"),
    path("<int:taggregation_pk>/<str:slug>/", views.agg_index, name="agg_index"),
    path(
        "<int:taggregation_pk>/<str:slug>/page/<int:page_num>/",
        views.agg_index,
        name="agg_index_page",
    ),
    path("all/", stories.all_stories, name="all_stories"),
    path("all/page/<int:page_num>/", stories.all_stories, name="all_stories_page"),
    path("comments/", views.recent_comments, name="recent_comments"),
    path(
        "comments/page/<int:page_num>/",
        views.recent_comments,
        name="recent_comments_page",
    ),
    path("s/<int:story_pk>/<str:slug>/", stories.story, name="story"),
    path(
        "s/<int:story_pk>/<str:slug>/upvote/<int:comment_pk>/",
        views.upvote_comment,
        name="upvote_comment",
    ),
    path(
        "s/<int:story_pk>/<str:slug>/source/",
        views.comment_source,
        name="story_source",
    ),
    path(
        "s/<int:story_pk>/<str:slug>/source/<int:comment_pk>/",
        views.comment_source,
        name="comment_source",
    ),
    path(
        "s/<int:story_pk>/<str:slug>/cached/",
        stories.story_remote_content,
        name="story_remote_content",
    ),
    path("s/<int:story_pk>/<str:slug>/edit/", stories.edit_story, name="edit_story"),
    path("c/preview/", views.preview_comment, name="preview_comment"),
    path("c/<int:comment_pk>/edit/", views.edit_comment, name="edit_comment"),
    path("c/<int:comment_pk>/delete/", views.delete_comment, name="delete_comment"),
    path("search/", views.search, name="search"),
    path("u/<str:username>/", account.profile, name="profile"),
    path("u/<str:username>/posts/", account.profile_posts, name="profile_posts"),
    path(
        "u/<str:username>/posts/<int:page_num>/",
        account.profile_posts,
        name="profile_posts_page",
    ),
    path("submit/", stories.submit_story, name="submit"),
    path("reply/<int:comment_pk>/", views.reply, name="reply"),
    path("upvote/<int:story_pk>/", stories.upvote_story, name="upvote_story"),
    path("save/", account.bookmark_story, name="bookmark_story"),
    path("tag/<int:tag_pk>/<str:slug>/", tags.view_tag, name="view_tag"),
    path(
        "tag/<int:tag_pk>/<str:slug>/page/<int:page_num>/",
        tags.view_tag,
        name="view_tag_page",
    ),
    path("domain/<str:slug>/", views.domain, name="domain"),
    path("domain/<str:slug>/page/<int:page_num>/", views.domain, name="domain_page"),
    path("tags/", tags.browse_tags, name="browse_tags"),
    path("tags/page/<int:page_num>/", tags.browse_tags, name="browse_tags_page"),
    path("tags/edit/<int:tag_pk>/<str:slug>/", tags.edit_tag, name="edit_tag"),
    path("tags/add/", tags.add_tag, name="add_tag"),
    path(
        "tags/graph/",
        TemplateView.as_view(template_name="tags/tag_graph.html"),
        name="tag_graph",
    ),
    path("tags/graph-svg/", tags.tag_graph_svg, name="tag_graph_svg"),
    path("aggs/", tags.personal_aggregations, name="personal_aggregations"),
    path(
        "aggs/page/<int:page_num>/",
        tags.personal_aggregations,
        name="personal_aggregations_page",
    ),
    path("aggs/all/", tags.public_aggregations, name="public_aggregations"),
    path(
        "aggs/all/page/<int:page_num>/",
        tags.public_aggregations,
        name="public_aggregations_page",
    ),
    path("aggs/default/", tags.default_aggregations, name="default_aggregations"),
    path(
        "aggs/default/page/<int:page_num>/",
        tags.default_aggregations,
        name="default_aggregations_page",
    ),
    path(
        "agg/<int:taggregation_pk>/<str:slug>/", tags.taggregation, name="taggregation"
    ),
    path(
        "agg/change-subscription/<int:taggregation_pk>/",
        tags.taggregation_change_subscription,
        name="taggregation_change_subscription",
    ),
    path(
        "agg/copy/<int:taggregation_pk>/",
        tags.copy_taggregation,
        name="copy_taggregation",
    ),
    path(
        "agg/edit/<int:taggregation_pk>/<str:slug>/",
        tags.edit_aggregation,
        name="edit_aggregation",
    ),
    path(
        "agg/edit/<int:taggregation_pk>/<str:slug>/<int:taggregationhastag_id>/",
        tags.edit_aggregation_filter,
        name="edit_aggregation_filter",
    ),
    path(
        "agg/edit/<int:taggregation_pk>/<str:slug>/new/",
        tags.new_aggregation_filter,
        name="new_aggregation_filter",
    ),
    path(
        "agg/edit/<int:taggregation_pk>/delete-filter/",
        tags.delete_aggregation_filter,
        name="delete_aggregation_filter",
    ),
    path("agg/new/", tags.new_aggregation, name="new_aggregation"),
    path("accounts/auth_token/new/", account.issue_token, name="issue_token"),
    path(
        "accounts/invitations/requests/",
        account.invitation_requests,
        name="invitation_requests",
    ),
    path(
        "accounts/invitations/requests/new/",
        RedirectView.as_view(url="/accounts/signup-help/", permanent=False),
        name="new_invitation_request",
    ),
    path("accounts/invitations/new/", account.generate_invite, name="generate_invite"),
    path(
        "accounts/invitations/new/<uuid:invite_pk>/",
        account.generate_invite,
        name="resend_invite",
    ),
    path(
        "accounts/signup-help/",
        account.new_invitation_request,
        name="signup_help",
    ),
    path(
        "accounts/welcome/",
        account.welcome,
        name="welcome",
    ),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(
            template_name="account/login.html", authentication_form=AuthenticationForm
        ),
        name="login",
    ),
    path(
        "accounts/logout/",
        auth_views.LogoutView.as_view(next_page="index"),
        name="logout",
    ),
    path(
        "accounts/password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="account/password_reset.html"
        ),
        name="password_reset",
    ),
    path("accounts/", account.view_account, name="account"),
    path("accounts/activity/", account.my_activity, name="account_activity"),
    path(
        "accounts/activity/page/<int:page_num>",
        account.my_activity,
        name="account_activity_page",
    ),
    path(
        "accounts/password-change/",
        auth_views.PasswordChangeView.as_view(
            template_name="account/password_change.html", success_url="/accounts"
        ),
        name="password_change",
    ),
    path("accounts/bookmarks/", account.bookmarks, name="bookmarks"),
    path(
        "accounts/bookmarks/page/<int:page_num>/",
        account.bookmarks,
        name="bookmarks_page",
    ),
    path("accounts/bookmarks.json", account.bookmarks_json, name="bookmarks_json"),
    path(
        "accounts/bookmarks/edit-comment/<int:bookmark_pk>/",
        account.edit_comment_bookmark,
        name="edit_comment_bookmark",
    ),
    path(
        "accounts/bookmarks/edit-story/<int:bookmark_pk>/",
        account.edit_story_bookmark,
        name="edit_story_bookmark",
    ),
    path("accounts/profile/edit/", account.edit_profile, name="edit_profile"),
    path("accounts/profile/avatar/", account.edit_avatar, name="edit_avatar"),
    path("accounts/settings/", account.edit_settings, name="edit_settings"),
    path("accounts/inbox/", account.inbox, name="inbox"),
    path(
        "accounts/inbox/<int:message_pk>/", account.inbox_message, name="inbox_message"
    ),
    path(
        "accounts/inbox/<int:message_pk>/raw/",
        account.inbox_message_raw,
        name="inbox_message_raw",
    ),
    path("accounts/inbox/sent/", account.inbox_sent, name="inbox_sent"),
    path(
        "accounts/inbox/<int:in_reply_to>/reply/",
        account.inbox_compose,
        name="inbox_reply",
    ),
    path("accounts/inbox/compose/", account.inbox_compose, name="inbox_compose"),
    path(
        "accounts/invitation/<uuid:invite_pk>/",
        account.accept_invite,
        name="accept_invite",
    ),
    path("accounts/notifications/", account.notifications, name="notifications"),
    path("accounts/hats/edit/<int:hat_pk>/", account.edit_hat, name="edit_hat"),
    path("accounts/hats/create/", account.edit_hat, name="new_hat"),
    path("feeds/latest.rss", LatestStoriesRss(), name="latest_stories_rss"),
    path("feeds/latest.atom", LatestStoriesAtom(), name="latest_stories_atom"),
    path("feeds/<str:username>/latest.rss", user_feeds_rss, name="user_feeds_rss"),
    path("feeds/<str:username>/latest.atom", user_feeds_atom, name="user_feeds_atom"),
    path(
        "favicon.ico",
        RedirectView.as_view(url="static/favicon.ico", permanent=False),
        name="favicon",
    ),
    path(".well-known/webfinger/", webfinger, name="webfinger"),
    path("webmention/", webmention_endpoint, name="webmention_endpoint"),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


@cache_page(60 * 60 * 24)
def response_400_handler(request, exception=None):
    return render(request, "400.html", status=400, context={"exception": exception})


@cache_page(60 * 60 * 24)
def response_403_handler(request, exception=None):
    return render(request, "403.html", status=403, context={"exception": exception})


@cache_page(60 * 60 * 24)
def response_404_handler(request, exception=None):
    return render(request, "404.html", status=404)


@cache_page(60 * 60 * 24)
def response_500_handler(request, exception=None):
    return render(request, "500.html", status=500)


handler400 = "sic.urls.response_400_handler"
handler403 = "sic.urls.response_403_handler"
handler404 = "sic.urls.response_404_handler"
handler500 = "sic.urls.response_500_handler"
