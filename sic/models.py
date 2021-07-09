from datetime import datetime, timedelta
import string
import uuid
from django.db import models
from django.contrib.auth.models import (
    BaseUserManager,
    AbstractBaseUser,
    PermissionsMixin,
)
from django.contrib import messages
from django.urls import reverse
from django.utils.text import slugify
from django.utils.timezone import make_aware
from django.core.mail import send_mail
from .apps import SicAppConfig as config

url_decode_translation = str.maketrans(string.ascii_lowercase[:10], string.digits)
url_encode_translation = str.maketrans(string.digits, string.ascii_lowercase[:10])


class Domain(models.Model):
    id = models.AutoField(primary_key=True)
    url = models.URLField(null=False, blank=False)


class StoryKind(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(null=False, blank=False, max_length=40, unique=True)
    hex_color = models.CharField(max_length=7, null=True, blank=True, default="#fffff")
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name}"

    def color_vars_css(self):
        h = self.hex_color.lstrip("#")
        r, g, b = tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
        return f"--red: {r}; --green:{g}; --blue:{b};"

    def default_value():
        val, _ = StoryKind.objects.get_or_create(name="article")
        return val


class Story(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        "User", related_name="stories", on_delete=models.CASCADE, null=False
    )
    title = models.CharField(null=False, blank=False, max_length=100)
    description = models.TextField(null=True, blank=True)
    url = models.URLField(null=True)
    created = models.DateTimeField(auto_now_add=True)
    publish_date = models.DateField(null=True, blank=True)

    domain = models.ForeignKey(Domain, on_delete=models.SET_NULL, null=True, blank=True)
    merged_into = models.ForeignKey(
        "Story", on_delete=models.CASCADE, null=True, blank=True
    )
    active = models.BooleanField(default=True, null=False)
    user_is_author = models.BooleanField(default=False, null=False)
    tags = models.ManyToManyField("Tag", related_name="stories", blank=True)
    kind = models.ManyToManyField(
        "StoryKind",
        related_name="stories",
        blank=False,
    )

    def __str__(self):
        return f"{self.title}"

    def slugify(self):
        return slugify(self.title, allow_unicode=True)

    def get_absolute_url(self):

        return reverse(
            "story",
            kwargs={"story_pk": self.pk, "slug": self.slugify()},
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

    def get_absolute_url(self):
        return self.story.get_absolute_url() + f"#{self.slugify()}"

    def slugify(self) -> str:
        return str(self.id).translate(url_encode_translation)

    @staticmethod
    def deslugify(slug: str):
        return int(slug.translate(url_decode_translation))

    def karma(self):
        return self.votes.count()


class Tag(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(null=False, blank=False, max_length=40, unique=True)
    hex_color = models.CharField(max_length=7, null=True, blank=True, default="#fffff")
    created = models.DateTimeField(auto_now_add=True)
    parents = models.ManyToManyField("Tag", related_name="children", blank=True)

    def __str__(self):
        return f"{self.name}"

    def color_vars_css(self):
        h = self.hex_color.lstrip("#")
        r, g, b = tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
        return f"--red: {r}; --green:{g}; --blue:{b};"

    def get_stories(self):
        return self.stories.all().union(
            *list(map(lambda t: t.get_stories(), self.children.all()))
        )


class Taggregation(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(null=False, blank=False, max_length=20)
    description = models.TextField(null=True, blank=True)
    creator = models.ForeignKey(
        "User",
        related_name="created_taggregations",
        null=False,
        blank=False,
        on_delete=models.PROTECT,
    )
    moderators = models.ManyToManyField(
        "User", related_name="moderated_taggregations", blank=False
    )
    tags = models.ManyToManyField("Tag", blank=False)
    created = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now_add=True, null=False, blank=False)
    default = models.BooleanField(default=False, null=False, blank=False)
    discoverable = models.BooleanField(default=False, null=False, blank=False)
    private = models.BooleanField(default=True, null=False, blank=False)

    def __str__(self):
        return f"{self.name}"

    def slugify(self):
        return slugify(self.name, allow_unicode=True)

    def get_absolute_url(self):
        return reverse(
            "taggregation",
            kwargs={"taggregation_pk": self.pk, "slug": self.slugify()},
        )

    def user_has_access(self, user):
        if user.is_authenticated:
            return (not self.private) or (
                (user.pk == self.creator.pk) or (user in self.moderators.all())
            )
        else:
            return not self.private

    def user_can_modify(self, user):
        if not self.user_has_access(user):
            return False
        return (user.pk == self.creator.pk) or (user in self.moderators.all())

    def get_stories(self):
        return Story.objects.none().union(
            *list(map(lambda t: t.get_stories(), self.tags.all()))
        )


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
        root_url = request.get_host()
        body = f"{config.INVITATION_BODY}\n\n{root_url}{self.get_absolute_url()}"
        try:
            send_mail(
                config.INVITATION_SUBJECT,
                body,
                config.INVITATION_FROM,
                [self.address],
                fail_silently=False,
            )
            messages.add_message(
                request,
                messages.SUCCESS,
                f"Successfully sent invitation to {self.address}.",
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
    user = models.ForeignKey(
        "User", related_name="hats", on_delete=models.CASCADE, null=False
    )


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


class User(PermissionsMixin, AbstractBaseUser):
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
    taggregation_subscriptions = models.ManyToManyField(Taggregation, blank=True)

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

    saved_comments = models.ManyToManyField(
        Comment,
        through="CommentBookmark",
        related_name="saved_by",
        through_fields=("user", "comment"),
        blank=True,
    )
    saved_stories = models.ManyToManyField(
        Story,
        through="StoryBookmark",
        related_name="saved_by",
        through_fields=("user", "story"),
        blank=True,
    )

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

    def is_new_user(self):
        return (make_aware(datetime.now()) - self.created) < timedelta(
            days=config.NEW_USER_DAYS
        ) and not self.is_staff

    @property
    def is_staff(self):
        "Is the user a member of staff?"
        # Simplest possible answer: All admins are staff
        return self.is_admin


class CommentBookmark(models.Model):
    id = models.AutoField(primary_key=True)
    comment = models.ForeignKey(Comment, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)
    annotation = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = ["comment", "user"]


class StoryBookmark(models.Model):
    id = models.AutoField(primary_key=True)
    story = models.ForeignKey(Story, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)
    annotation = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = ["story", "user"]

    def __str__(self):
        return f"{self.id} {self.story} {self.user} {self.created}"
