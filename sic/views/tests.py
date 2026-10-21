from datetime import datetime, timedelta

from django.db import transaction, connection, IntegrityError
from django.test import TestCase
from django.utils import timezone
from django.utils.timezone import make_aware
from django.contrib.auth import authenticate, login as auth_login
from django.test import Client
from django.urls import reverse
from urllib.parse import urlencode

from sic.models import (
    Story,
    StoryKind,
    Comment,
    Notification,
    StoryRemoteContent,
    Tag,
    User,
)
from sic.forms import SubmitStoryForm


class StorySubmit(TestCase):
    def setUp(self):
        StoryKind.objects.get_or_create(name=StoryKind.DEFAULT_NAME)
        admin = User.objects.create_user("admin@example.com", "hunter2")
        admin.is_admin = True
        admin.save()
        user = User.objects.create_user("user@example.com", "hunter3")
        _, _ = admin.invited.get_or_create(
            inviter=admin,
            receiver=user,
            address=user.email,
            accepted=make_aware(datetime.now()),
        )

    def test_story_submit(self):
        """ """
        self.assertEqual(User.objects.filter(email="admin@example.com").count(), 1)
        staff = User.objects.get(email="admin@example.com")
        user = User.objects.get(email="user@example.com")

        client = Client()
        response = client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        response = client.post(
            reverse("login"),
            params={"username": "user@example.com", "password": "hunter3"},
        )

        form = SubmitStoryForm(
            data={
                "url": "foo",
                "kind": StoryKind.objects.get(name=StoryKind.DEFAULT_NAME),
            }
        )
        self.assertFalse(form.is_valid())
        self.assertEqual(form.errors["url"], ["Enter a valid URL."])
        form = SubmitStoryForm(
            data={
                "url": "http://example.com",
                "kind": [StoryKind.objects.get(name=StoryKind.DEFAULT_NAME)],
            }
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["url"], "http://example.com")

        form = SubmitStoryForm(
            data={
                "url": "https://youtube.com?si=creep&v=foo&kw=weirdo",
                "kind": [StoryKind.objects.get(name=StoryKind.DEFAULT_NAME)],
            }
        )
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["url"], "https://youtube.com?v=foo")
