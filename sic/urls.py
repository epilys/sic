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
from .views import *
from .feeds import *

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", index, name="index"),
    path("about/", about, name="about"),
    path("page/<int:page_num>/", index, name="index_page"),
    path("recent", recent, name="recent"),
    path("recent/page/<int:page_num>/", recent, name="recent_page"),
    path("comments", recent_comments, name="recent_comments"),
    path("comments/page/<int:page_num>/", recent_comments, name="recent_comments_page"),
    path("s/<int:story_pk>/<slug:slug>/", story, name="story"),
    path(
        "s/<int:story_pk>/<slug:slug>/upvote/<int:comment_pk>/",
        upvote_comment,
        name="upvote_comment",
    ),
    path("s/<int:story_pk>/<slug:slug>/edit", edit_story, name="edit_story"),
    path("u/<str:username>/", profile, name="profile"),
    path("u/<str:username>/posts", profile_posts, name="profile_posts"),
    path(
        "u/<str:username>/posts/<int:page_num>",
        profile_posts,
        name="profile_posts_page",
    ),
    path("submit/", submit_story, name="submit"),
    path("reply/<int:comment_pk>", reply, name="reply"),
    path("upvote/<int:story_pk>/", upvote_story, name="upvote_story"),
    path("save/<int:story_pk>/", save_story, name="save_story"),
    path("tags/", browse_tags, name="browse_tags"),
    path("tags/page/<int:page_num>/", browse_tags, name="browse_tags_page"),
    path("tags/edit/<int:tag_pk>/<slug:slug>", edit_tag, name="edit_tag"),
    path("tags/add/", add_tag, name="add_tag"),
    path("agg/<int:taggregation_pk>/<slug:slug>/", taggregation, name="taggregation"),
    path(
        "agg/change-subscription/<int:taggregation_pk>/",
        taggregation_change_subscription,
        name="taggregation_change_subscription",
    ),
    path("accounts/invitations/new", generate_invite, name="generate_invite"),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "accounts/password-reset/",
        auth_views.PasswordResetView.as_view(template_name="password_reset.html"),
        name="password_reset",
    ),
    path("accounts/", view_account, name="account"),
    path("accounts/bookmarks", bookmarks, name="bookmarks"),
    path("accounts/bookmarks/page/<int:page_num>/", bookmarks, name="bookmarks_page"),
    path(
        "accounts/bookmarks/edit/<int:bookmark_pk>", edit_bookmark, name="edit_bookmark"
    ),
    path("accounts/profile/edit", edit_profile, name="edit_profile"),
    path("accounts/profile/avatar", edit_avatar, name="edit_avatar"),
    path("accounts/inbox/", inbox, name="inbox"),
    path("accounts/invitation/<uuid:invite_pk>", accept_invite, name="accept_invite"),
    path("feeds/latest.rss", LatestStoriesRss(), name="latest_stories_rss"),
    path("feeds/latest.atom", LatestStoriesAtom(), name="latest_stories_atom"),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
