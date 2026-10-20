from datetime import datetime, timedelta

from django.db import transaction, connection, IntegrityError
from django.test import TestCase
from django.utils import timezone
from django.utils.timezone import make_aware

from .models import User, Invitation, Tag


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

        created = False
        try:
            inv, created = user.invited.get_or_create(
                inviter=user,
                receiver=staff,
                address=staff.email,
                accepted=make_aware(datetime.now()),
            )
        except IntegrityError:
            pass
        self.assertFalse(created)
        try:
            inv, created = staff.invited.get_or_create(
                inviter=staff,
                receiver=user,
                address=user.email,
                accepted=make_aware(datetime.now()),
            )
        except IntegrityError:
            pass
        self.assertFalse(created)
        inv, created = user.invited.get_or_create(
            inviter=user,
            receiver=user2,
            address=user2.email,
            accepted=make_aware(datetime.now()),
        )
        self.assertTrue(created)
        created = False

        try:
            inv, created = user2.invited.get_or_create(
                inviter=user2,
                receiver=staff,
                address=staff.email,
                accepted=make_aware(datetime.now()),
            )
        except IntegrityError:
            pass

        self.assertFalse(created)

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
        created = False
        try:
            with transaction.atomic():
                root.parents.set([child])
            created = True
        except IntegrityError:
            pass
        self.assertFalse(created)
        leaf = Tag.objects.get(name="leaf")

        root.parents.set([leaf])
        try:
            with transaction.atomic():
                leaf.parents.set([child])
            created = True
        except IntegrityError:
            pass
        self.assertFalse(created)
        with transaction.atomic():
            child.parents.set([leaf])
