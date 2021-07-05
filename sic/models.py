from django.db import models
from django.db.models import Count
from django.contrib.auth.models import BaseUserManager, AbstractBaseUser
from django.urls import reverse
from django.utils.text import slugify
from django.utils.timezone import make_aware
from django.core.mail import send_mail
from .apps import SicAppConfig as config
import uuid
from datetime import datetime


class Domain(models.Model):
    id = models.AutoField(primary_key=True)
    url = models.URLField(null=False, blank=False)


class Story(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        "User", related_name="stories", on_delete=models.CASCADE, null=False
    )
    title = models.CharField(null=False, blank=False, max_length=100)
    description = models.TextField(null=True, blank=True)
    url = models.URLField(null=True)
    created = models.DateTimeField(auto_now_add=True)

    domain = models.ForeignKey(Domain, on_delete=models.SET_NULL, null=True, blank=True)
    merged_into = models.ForeignKey(
        "Story", on_delete=models.CASCADE, null=True, blank=True
    )
    active = models.BooleanField(default=True, null=False)
    user_is_author = models.BooleanField(default=False, null=False)
    tags = models.ManyToManyField("Tag", blank=True)

    def __str__(self):
        return f"{self.title}"

    def slugify(self):
        return slugify(self.title, allow_unicode=True)

    def get_absolute_url(self):

        return reverse(
            "story",
            kwargs={"pk": self.pk, "slug": self.slugify()},
        )

    def karma(self):
        return self.votes.filter(comment=None).count()

    def get_listing_url(self):
        return (
            self.get_absolute_url()
            if self.url is None or len(self.url) == 0
            else self.url
        )


class Message(models.Model):
    id = models.AutoField(primary_key=True)
    recipient = models.ForeignKey(
        "User", related_name="received_messages", on_delete=models.SET_NULL, null=True
    )
    read_by_recipient = models.BooleanField(default=False, null=False)
    author = models.ForeignKey(
        "User", related_name="sent_messages", on_delete=models.SET_NULL, null=True
    )
    hat = models.ForeignKey("Hat", on_delete=models.SET_NULL, null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    subject = models.CharField(null=False, blank=True, max_length=100)
    body = models.TextField(null=True, blank=False)

    def __str__(self):
        return f"{self.author} {self.subject}"


class Comment(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        "User", related_name="comments", on_delete=models.CASCADE, null=False
    )
    story = models.ForeignKey(
        "Story", related_name="comments", on_delete=models.CASCADE, null=False
    )
    parent = models.ForeignKey(
        "Comment",
        related_name="replies",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    hat = models.ForeignKey(
        "Hat", on_delete=models.SET_NULL, null=True, blank=True, default=None
    )
    deleted = models.BooleanField(default=False, null=False, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    text = models.TextField(null=True, blank=False)

    def __str__(self):
        return f"{self.user} {self.created}"

    def karma(self):
        return self.votes.count()


class Tag(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(null=False, blank=False, max_length=20)
    hex_color = models.CharField(max_length=7, null=True, blank=True, default="#fffff")

    def __str__(self):
        return f"{self.name}"


class TagFilter(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(null=False, blank=False, max_length=20)

    def __str__(self):
        return f"{self.name}"


class Invitation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    inviter = models.ForeignKey(
        "User", related_name="invited", on_delete=models.SET_NULL, null=True
    )
    receiver = models.OneToOneField(
        "User",
        related_name="invited_by",
        on_delete=models.SET_NULL,
        null=True,
        default=None,
    )
    address = models.EmailField(null=False, blank=False)
    created = models.DateTimeField(auto_now_add=True)
    accepted = models.DateTimeField(null=True, blank=True)

    def send(self, request):
        try:
            send_mail(
                config.INVITATION_SUBJECT,
                f"{config.INVITATION_BODY}\n\n{self.get_absolute_url()}",
                config.INVITATION_FROM,
                [self.address],
                fail_silently=False,
            )
        except Exception as error:
            messages.add_message(
                request, messages.ERROR, f"Could not send invitation. Error: {error}"
            )

    def is_valid(self):
        return self.accepted is None

    def get_absolute_url(self):
        return reverse("accept_invite", args=[self.id])

    def accept(self, user):
        self.accepted = make_aware(datetime.now())
        self.receiver = user
        self.save()


class Vote(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        "User", related_name="votes", on_delete=models.CASCADE, null=False
    )
    story = models.ForeignKey(
        Story, related_name="votes", on_delete=models.CASCADE, null=False
    )
    comment = models.ForeignKey(
        Comment, related_name="votes", on_delete=models.CASCADE, null=True
    )
    created = models.DateTimeField(auto_now_add=True)


class Moderation(models.Model):
    id = models.AutoField(primary_key=True)


class Hat(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(null=False, blank=False, max_length=30)


class UserManager(BaseUserManager):
    def create_user(self, email, password=None):
        """
        Creates and saves a User with the given email, date of
        birth and password.
        """
        if not email:
            raise ValueError("Users must have an email address")

        user = self.model(
            email=self.normalize_email(email),
        )

        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None):
        """
        Creates and saves a superuser with the given email, date of
        birth and password.
        """
        user = self.create_user(
            email,
            password=password,
        )
        user.is_admin = True
        user.save(using=self._db)
        return user


class User(AbstractBaseUser):
    id = models.AutoField(primary_key=True)
    username = models.CharField(null=True, blank=True, unique=True, max_length=100)
    email = models.EmailField(
        verbose_name="email address",
        max_length=255,
        unique=True,
    )
    created = models.DateTimeField(auto_now_add=True)
    about = models.TextField(null=True, blank=True)
    avatar = models.CharField(null=True, blank=True, editable=False, max_length=8196)
    banned_by_user = models.OneToOneField(
        "User",
        related_name="banned_by",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    disabled_invite_by_user = models.OneToOneField(
        "User", on_delete=models.CASCADE, null=True, blank=True
    )

    email_notifications = models.BooleanField(default=False, null=False)
    email_replies = models.BooleanField(default=False, null=False)

    email_messages = models.BooleanField(default=False, null=False)
    email_mentions = models.BooleanField(default=False, null=False)
    show_avatars = models.BooleanField(default=True, null=False)
    show_story_previews = models.BooleanField(default=False, null=False)
    show_submitted_story_threads = models.BooleanField(default=False, null=False)
    github_username = models.CharField(null=True, blank=True, max_length=500)
    homepage = models.URLField(null=True, blank=True)

    is_active = models.BooleanField(default=True)
    is_admin = models.BooleanField(default=False)
    is_moderator = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.username if self.username else self.email

    def karma(self):
        return Vote.objects.all().filter(story__user=self, comment=None).count()

    def get_absolute_url(self):
        return reverse(
            "profile",
            kwargs={"username": self.username if self.username else self.pk},
        )

    def has_perm(self, perm, obj=None):
        "Does the user have a specific permission?"
        # Simplest possible answer: Yes, always
        return True

    def has_module_perms(self, app_label):
        "Does the user have permissions to view the app `app_label`?"
        # Simplest possible answer: Yes, always
        return True

    @property
    def is_staff(self):
        "Is the user a member of staff?"
        # Simplest possible answer: All admins are staff
        return self.is_admin
