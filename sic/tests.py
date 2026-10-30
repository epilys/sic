from datetime import datetime, timedelta

from django.db import transaction, connection, IntegrityError
from django.test import TestCase, Client
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.utils.timezone import make_aware
from django.contrib.messages import get_messages

from .models import (
    User,
    Invitation,
    Tag,
    Story,
    Comment,
    StoryKind,
    Notification,
    Comment,
)
from .moderation import ModerationLogEntry


class InvitationCycleTests(TestCase):
    def setUp(self):
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
        user2 = User.objects.create_user("user2@example.com", "hunter4")

    def test_no_invite_cycle(self):
        """ """
        self.assertEqual(User.objects.filter(email="admin@example.com").count(), 1)
        staff = User.objects.get(email="admin@example.com")
        user = User.objects.get(email="user@example.com")
        user2 = User.objects.get(email="user2@example.com")

        self.assertRaises(
            IntegrityError,
            user.invited.get_or_create,
            inviter=user,
            receiver=staff,
            address=staff.email,
            accepted=make_aware(datetime.now()),
        )
        self.assertRaises(
            IntegrityError,
            staff.invited.get_or_create,
            inviter=staff,
            receiver=user,
            address=user.email,
            accepted=make_aware(datetime.now()),
        )
        _, created = user.invited.get_or_create(
            inviter=user,
            receiver=user2,
            address=user2.email,
            accepted=make_aware(datetime.now()),
        )
        self.assertTrue(created)

        self.assertRaises(
            IntegrityError,
            user2.invited.get_or_create,
            inviter=user2,
            receiver=staff,
            address=staff.email,
            accepted=make_aware(datetime.now()),
        )

    def test_invite_permissions(self):
        """ """
        staff = User.objects.get(email="admin@example.com")
        user = User.objects.get(email="user@example.com")
        user2 = User.objects.get(email="user2@example.com")

        self.assertFalse(staff.can_be_vouched)
        self.assertFalse(user.can_be_vouched)

        self.assertFalse(user2.can_be_vouched)

        user2.is_active = True
        user2.save()
        self.assertFalse(user2.can_be_vouched)
        user2.email_validated = True
        user2.save()

        self.assertTrue(user2.can_be_vouched)

        user2.is_banned = True
        user2.save()

        self.assertFalse(user2.can_be_vouched)

        user2.is_banned = False
        user2.is_moderator = False
        user2.save()
        self.assertTrue(user2.can_be_vouched)
        _, _ = staff.invited.get_or_create(
            inviter=staff,
            receiver=user2,
            address=user2.email,
            accepted=make_aware(datetime.now()),
        )
        self.assertFalse(user2.can_be_vouched)


class TagCycleTests(TestCase):
    def setUp(self):
        root_tag = Tag.objects.create(name="root")
        child_tag = Tag.objects.create(name="child")
        child_tag.parents.set([root_tag])
        leaf = Tag.objects.create(name="leaf")

    def test_no_tag_cycle(self):
        """ """
        root = Tag.objects.get(name="root")
        child = Tag.objects.get(name="child")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                root.parents.set([child])

        leaf = Tag.objects.get(name="leaf")

        root.parents.set([leaf])
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                leaf.parents.set([child])

        with transaction.atomic():
            child.parents.set([leaf])


class PostingTests(TestCase):
    def setUp(self):
        admin = User.objects.create_user("admin@example.com", "hunter2")
        admin.is_admin = True
        admin.save()
        user = User.objects.create_user("user@example.com", "hunter3")
        user.email_validated = True
        user.save()
        _, _ = admin.invited.get_or_create(
            inviter=admin,
            receiver=user,
            address=user.email,
            accepted=make_aware(datetime.now()),
        )
        user2 = User.objects.create_user("user2@example.com", "hunter4")
        tag = Tag.objects.create(name="root")

        self.admin = admin
        self.user = user
        self.user2 = user2
        self.tag = tag

    def test_posting(self):
        self.assertFalse(self.user2.can_participate)
        self.assertRaises(
            PermissionDenied,
            Story.objects.create,
            title="",
            url="",
            publish_date=None,
            description=None,
            user=self.user2,
            user_is_author=False,
            requires_javascript=False,
            content_warning=None,
        )
        story_obj = Story.objects.create(
            title="",
            url="",
            publish_date=None,
            description=None,
            user=self.user,
            user_is_author=False,
            requires_javascript=False,
            content_warning=None,
        )
        story_obj.title = "foo"
        c = Client()
        c.force_login(self.user2)

        self.assertEqual(c.post("/submit/").status_code, 403)
        c = Client()
        c.force_login(self.user)
        self.assertTrue(self.user.can_participate)
        response = c.post("/submit/")
        self.assertEqual(response.status_code, 200)
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertEqual(
            messages,
            [
                "Invalid form. Error: title: This field is required., kind: This field is required."
            ],
        )

        response = c.post("/submit/", {"title": "foo"})
        self.assertEqual(response.status_code, 200)
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertEqual(
            messages, ["Invalid form. Error: kind: This field is required."]
        )

        response = c.post("/submit/", {"title": "foo", "kind": "article"})
        self.assertEqual(response.status_code, 200)
        messages = [m.message for m in get_messages(response.wsgi_request)]
        self.assertEqual(
            messages, ["Invalid form. Error: kind: “article” is not a valid value."]
        )

        article_kind = StoryKind.default_value()

        response = c.post("/submit/", {"title": "foo", "kind": article_kind.pk})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/2/foo/")

        self.user.email_validated = False
        self.user.save()

        response = c.post("/submit/", {"title": "foo2", "kind": article_kind.pk})
        self.assertEqual(response.status_code, 403)

        self.user.email_validated = True
        self.user.save()
        response = c.post(
            "/s/2/foo/edit/",
            {"title": "foo3", "kind": article_kind.pk, "reason": "changed title"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/2/foo3/")
        self.assertEqual(ModerationLogEntry.objects.all().count(), 1)
        modlog = ModerationLogEntry.objects.all()[0]
        self.assertEqual(modlog.user, self.user)
        self.assertEqual(modlog.action, "Set story title to foo3")
        self.assertEqual(modlog.reason, "changed title")
        self.assertEqual(Notification.objects.all().count(), 0)

        response = c.post("/s/2/foo3/", {"text": "my comment"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/2/foo3/#b")

        """
        Now login as admin, perform moderation actions and confirm the user receives a notification and an entry is added in the moderation log.
        """
        c = Client()
        c.force_login(self.admin)

        """
        Edit story title
        """
        response = c.post(
            "/s/2/foo2/edit/",
            {"title": "foo4", "kind": article_kind.pk, "reason": "changed title again"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/2/foo4/")
        self.assertEqual(ModerationLogEntry.objects.all().count(), 2)
        modlog = ModerationLogEntry.objects.latest("action_time")
        self.assertEqual(modlog.user, self.admin)
        self.assertEqual(modlog.action, "Set story title to foo4")
        self.assertEqual(modlog.reason, "changed title again")
        self.assertEqual(Notification.objects.all().count(), 1)
        notif = Notification.objects.latest("created")
        self.assertEqual(notif.user, self.user)
        self.assertEqual(notif.caused_by, self.admin)
        self.assertEqual(notif.kind, Notification.Kind.MODERATION)
        self.assertEqual(notif.name, "admin@example.com has edited your story title")
        self.assertEqual(notif.body, "Reason was: changed title again.")
        self.assertEqual(notif.url, "/s/2/foo4/")

        """
        Edit story description
        """

        response = c.post(
            "/s/2/foo2/edit/",
            {
                "title": "foo4",
                "kind": article_kind.pk,
                "description": "foo",
                "reason": "none",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/2/foo4/")
        self.assertEqual(ModerationLogEntry.objects.all().count(), 3)
        modlog = ModerationLogEntry.objects.latest("action_time")
        self.assertEqual(modlog.user, self.admin)
        self.assertEqual(modlog.action, "Set story description to foo")
        self.assertEqual(modlog.reason, "none")
        self.assertEqual(Notification.objects.all().count(), 2)
        notif = Notification.objects.latest("created")
        self.assertEqual(notif.user, self.user)
        self.assertEqual(notif.caused_by, self.admin)
        self.assertEqual(notif.kind, Notification.Kind.MODERATION)
        self.assertEqual(
            notif.name, "admin@example.com has edited your story description"
        )
        self.assertEqual(notif.body, "Reason was: none.")
        self.assertEqual(notif.url, "/s/2/foo4/")

        """
        Edit story content warning
        """

        response = c.post(
            "/s/2/foo2/edit/",
            {
                "title": "foo4",
                "kind": article_kind.pk,
                "description": "foo",
                "content_warning": "foobar",
                "reason": "none",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/2/foo4/")
        self.assertEqual(ModerationLogEntry.objects.all().count(), 4)
        modlog = ModerationLogEntry.objects.latest("action_time")
        self.assertEqual(modlog.user, self.admin)
        self.assertEqual(modlog.action, 'Set story\'s content warning to "foobar"')
        self.assertEqual(modlog.reason, "none")
        self.assertEqual(Notification.objects.all().count(), 3)
        notif = Notification.objects.latest("created")
        self.assertEqual(notif.user, self.user)
        self.assertEqual(notif.caused_by, self.admin)
        self.assertEqual(notif.kind, Notification.Kind.MODERATION)
        self.assertEqual(
            notif.name, "admin@example.com has edited your story's content warning"
        )
        self.assertEqual(notif.body, "Reason was: none.")
        self.assertEqual(notif.url, "/s/2/foo4/")

        """
        Edit comment
        """
        response = c.post(
            "/c/1/edit/", {"text": "edited comment", "edit_reason": "power trip"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/s/2/foo4/#b")

        notif = Notification.objects.latest("created")
        self.assertEqual(notif.user, self.user)
        self.assertEqual(notif.caused_by, self.admin)
        self.assertEqual(notif.kind, Notification.Kind.MODERATION)
        self.assertEqual(notif.name, "admin@example.com has edited your comment")
        self.assertEqual(notif.body, "Reason was: power trip.")
        self.assertEqual(notif.url, "/s/2/foo4/#b")
