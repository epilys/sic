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
    path("page/<int:page_num>/", index, name="index_page"),
    path("recent", recent, name="recent"),
    path("recent/page/<int:page_num>/", recent, name="recent_page"),
    path("comments", recent_comments, name="recent_comments"),
    path("comments/page/<int:page_num>/", recent_comments, name="recent_comments_page"),
    path("s/<int:pk>/<slug:slug>/", story, name="story"),
    path(
        "s/<int:story_pk>/<slug:slug>/upvote/<int:comment_pk>/",
        upvote_comment,
        name="upvote_comment",
    ),
    path("s/<int:pk>/<slug:slug>/edit", edit_story, name="edit_story"),
    path("u/<str:username>/", profile, name="profile"),
    path("u/<str:username>/posts", profile_posts, name="profile_posts"),
    path(
        "u/<str:username>/posts/<int:page_num>",
        profile_posts,
        name="profile_posts_page",
    ),
    path("submit/", submit_story, name="submit"),
    path("reply/<int:comment_pk>", reply, name="reply"),
    path("upvote/<int:pk>/", upvote_story, name="upvote_story"),
    path("accounts/invitations/new", generate_invite, name="generate_invite"),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    path(
        "accounts/password-reset/",
        auth_views.LoginView.as_view(template_name="login.html"),
        name="password_reset",
    ),
    path("accounts/", account, name="account"),
    path("accounts/profile/edit", edit_profile, name="edit_profile"),
    path("accounts/profile/avatar", edit_avatar, name="edit_avatar"),
    path("accounts/inbox/", inbox, name="inbox"),
    path("accounts/invitation/<uuid:pk>", accept_invite, name="accept_invite"),
    path("feeds/latest.rss", LatestStoriesRss(), name="latest_stories_rss"),
    path("feeds/latest.atom", LatestStoriesAtom(), name="latest_stories_atom"),
] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
