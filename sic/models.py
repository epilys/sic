from urllib.parse import urlparse
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
from django.utils.functional import cached_property
from django.core.mail import EmailMessage
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.sites.models import Site
from .apps import SicAppConfig as config
from .markdown import comment_to_html, Textractor
from .voting import story_hotness

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

    @staticmethod
    def default_value():
        val, _ = StoryKind.objects.get_or_create(name="article")
        return val

    class Meta:
        ordering = ["name"]


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

    class Meta:
        verbose_name_plural = "stories"

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

    def get_domain(self):
        if not self.url:
            return None
        o = urlparse(self.url).netloc
        if o.startswith("www."):
            o = o[4:]
        return o

    def hotness(self):
        return story_hotness(self)

    def description_to_html(self):
        return comment_to_html(self.description)

    def description_to_plain_text(self):
        return Textractor.extract(self.description_to_html()).strip()

    def active_comments(self):
        return self.comments.filter(deleted=False)


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

    def get_absolute_url(self):
        return reverse(
            "inbox_message",
            kwargs={"message_pk": self.pk},
        )


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

    def last_log_entry(self):
        from .moderation import ModerationLogEntry
        from django.contrib.contenttypes.models import ContentType

        entry = ModerationLogEntry.objects.filter(
            object_id=self.id,
            content_type=ContentType.objects.get(app_label="sic", model="comment"),
        ).latest("action_time")

        return entry

    def get_absolute_url(self):
        return self.story.get_absolute_url() + f"#{self.slugify()}"

    def slugify(self) -> str:
        return str(self.id).translate(url_encode_translation)

    @staticmethod
    def deslugify(slug: str):
        return int(slug.translate(url_decode_translation))

    def karma(self):
        return self.votes.count()

    def text_to_html(self):
        return comment_to_html(self.text)

    def text_to_plain_text(self):
        return Textractor.extract(self.text_to_html()).strip()


class Tag(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(null=False, blank=False, max_length=40, unique=True)
    hex_color = models.CharField(max_length=7, null=True, blank=True, default="#ffffff")
    created = models.DateTimeField(auto_now_add=True)
    parents = models.ManyToManyField("Tag", related_name="children", blank=True)

    def __str__(self):
        return f"{self.name}"

    def color_vars_css(self):
        h = self.hex_color.lstrip("#")
        r, g, b = tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))
        return f"--red: {r}; --green:{g}; --blue:{b};"

    def get_stories(self, depth=0):
        if depth == 0:
            return set(self.stories.all())
        if depth == -1:
            new_depth = depth
        else:
            new_depth = depth - 1
        ret = set(self.stories.all())
        for c in self.children.all():
            ret |= c.get_stories(new_depth)
        return ret

    def slugify(self):
        return slugify(self.name, allow_unicode=True)

    def hotness_modifier(self):
        return 0.0

    @cached_property
    def latest(self):
        stories = self.get_stories(-1)
        if stories.exists():
            return stories.latest("created")
        else:
            return None

    class Meta:
        ordering = ["name"]


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
    tags = models.ManyToManyField(
        "Tag", related_name="taggregations", through="TaggregationHasTag", blank=False
    )
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
        ret = set()
        for h in self.taggregationhastag_set.all():
            ret |= h.get_stories()
        return ret

    class Meta:
        ordering = ["name"]


class TaggregationHasTag(models.Model):
    id = models.AutoField(primary_key=True)
    taggregation = models.ForeignKey(Taggregation, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, null=True, blank=True, on_delete=models.CASCADE)
    depth = models.IntegerField(default=0, null=False, blank=False)

    def __str__(self):
        return f"{self.taggregation} {self.tag} depth={self.depth}"

    def get_stories(self):
        return set(self.tag.get_stories(self.depth))


class TagFilter(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(null=False, blank=False, max_length=20)

    def __str__(self):
        return f"{self.name}"


class InvitationRequest(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(null=False, blank=False, max_length=20)
    address = models.EmailField(null=False, blank=False, unique=True)
    about = models.TextField(null=False, blank=False)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.pk} {self.name} {self.address}"


class InvitationRequestVote(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey("User", on_delete=models.SET_NULL, null=True, blank=False)
    request = models.ForeignKey(
        InvitationRequest,
        related_name="votes",
        on_delete=models.CASCADE,
        null=False,
        blank=False,
    )
    in_favor = models.BooleanField(default=True, null=True, blank=True)
    note = models.TextField(null=False, blank=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [["user", "request"]]


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
        unique=True,
    )
    address = models.EmailField(null=False, blank=False, unique=True)
    created = models.DateTimeField(auto_now_add=True)
    accepted = models.DateTimeField(null=True, blank=True)

    def send(self, request):
        root_url = get_current_site(request).domain
        body = f"{config.INVITATION_BODY}\n\n{root_url}{self.get_absolute_url()}"
        try:
            EmailMessage(
                config.INVITATION_SUBJECT,
                body,
                config.INVITATION_FROM,
                [self.address],
                headers={"Message-ID": config.make_msgid()},
            ).send(fail_silently=False)
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

    class Meta:
        unique_together = ["user", "story", "comment"]


class Moderation(models.Model):
    id = models.AutoField(primary_key=True)


class Hat(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(null=False, blank=False, max_length=100)
    hex_color = models.CharField(max_length=7, null=True, blank=True, default="#000000")
    user = models.ForeignKey(
        "User", related_name="hats", on_delete=models.CASCADE, null=False
    )
    last_modified = models.DateTimeField(auto_now_add=True, null=False, blank=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["user", "name"]


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
    avatar_title = models.CharField(
        null=True, blank=True, editable=True, max_length=256
    )
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
    taggregation_subscriptions = models.ManyToManyField(
        Taggregation, related_name="subscribers", blank=True
    )

    # options
    email_notifications = models.BooleanField(default=True, null=False)
    email_replies = models.BooleanField(default=True, null=False)
    email_messages = models.BooleanField(default=True, null=False)
    email_mentions = models.BooleanField(default=True, null=False)
    show_avatars = models.BooleanField(default=True, null=False)
    show_story_previews = models.BooleanField(default=True, null=False)
    show_submitted_story_threads = models.BooleanField(default=True, null=False)
    show_colors = models.BooleanField(default=True, null=False)

    homepage = models.URLField(null=True, blank=True)
    git_repository = models.URLField(null=True, blank=True)
    metadata_1 = models.CharField(null=True, blank=True, max_length=200)
    metadata_2 = models.CharField(null=True, blank=True, max_length=200)
    metadata_3 = models.CharField(null=True, blank=True, max_length=200)
    metadata_4 = models.CharField(null=True, blank=True, max_length=200)
    metadata_1_label = models.CharField(null=True, blank=True, max_length=200)
    metadata_2_label = models.CharField(null=True, blank=True, max_length=200)
    metadata_3_label = models.CharField(null=True, blank=True, max_length=200)
    metadata_4_label = models.CharField(null=True, blank=True, max_length=200)

    auth_token = models.TextField(null=True, blank=True)

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

    def active_notifications(self):
        return self.notifications.filter(active=True).order_by("-created")

    def metadata_fields(self):
        ret = []
        if self.homepage and len(self.homepage) > 0:
            ret.append(("homepage", self.homepage))
        if self.git_repository and len(self.git_repository) > 0:
            ret.append(("git repository", self.git_repository))
        if self.metadata_1 and len(self.metadata_1) > 0:
            ret.append((self.metadata_1_label, self.metadata_1))
        if self.metadata_2 and len(self.metadata_2) > 0:
            ret.append((self.metadata_2_label, self.metadata_2))
        if self.metadata_3 and len(self.metadata_2) > 0:
            ret.append((self.metadata_3_label, self.metadata_3))
        if self.metadata_4 and len(self.metadata_4) > 0:
            ret.append((self.metadata_4_label, self.metadata_4))
        return ret

    def frontpage(self):
        taggregations = None
        if self.taggregation_subscriptions.exists():
            stories = set()
            for t in self.taggregation_subscriptions.all():
                stories |= t.get_stories()
            taggregations = list(self.taggregation_subscriptions.all())
            if len(taggregations) > 5:
                others = taggregations[5:]
                taggregations = taggregations[:5]
            else:
                others = None
            taggregations = {
                "list": taggregations,
                "others": others,
            }
        else:
            stories = Story.objects.filter(active=True)
        return {
            "stories": stories,
            "taggregations": taggregations,
        }


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


class Notification(models.Model):
    class Kind(models.TextChoices):
        REPLY = "RE", "New reply"
        MENTION = "MEN", "Mention"
        MESSAGE = "MSG", "New message"
        MODERATION = "MODR", "A moderator acted on your behalf"
        OTHER = "OTHR", "New notification"

    id = models.AutoField(primary_key=True)
    name = models.CharField(null=False, blank=False, max_length=20)
    body = models.TextField(null=False, blank=True)
    url = models.URLField(null=True, blank=True)
    user = models.ForeignKey(
        User, related_name="notifications", on_delete=models.CASCADE
    )
    caused_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE)
    kind = models.CharField(
        max_length=4,
        choices=Kind.choices,
        default=Kind.OTHER,
    )
    active = models.BooleanField(default=False, null=False)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} {self.kind}"

    def send(self, request=None):
        if request:
            domain = get_current_site(request).domain
        else:
            domain = Site.objects.get_current().domain
        root_url = f"http://{domain}"
        if self.caused_by:
            cause = str(self.caused_by)
        else:
            cause = "The system"
        if self.kind in {self.Kind.REPLY}:
            body = f"Visit {root_url}{self.url}"
        elif self.kind in {self.Kind.MESSAGE}:
            body = f"{cause} has sent you a message: {root_url}{self.url}"
        elif self.kind in {self.Kind.MODERATION}:
            body = f"A moderator has made changes regarding your content: {root_url}{self.url}"
        else:
            body = f"You have a new notification: {root_url}{self.url}"
        if len(self.body) > 0:
            body += "\n\n"
            body += self.body
        body += f"\n\nYou can disable email notifications in your account settings: {root_url}{reverse('edit_settings')}"
        try:
            EmailMessage(
                f"[sic] {self.name}",
                body,
                config.NOTIFICATION_FROM,
                [self.user.email],
                headers={"Message-ID": config.make_msgid()},
            ).send(fail_silently=False)
        except Exception as error:
            messages.add_message(
                request, messages.ERROR, f"Could not send notification. Error: {error}"
            )


class Webmention(models.Model):
    id = models.AutoField(primary_key=True)
    story = models.ForeignKey(
        Story, related_name="webmentions", on_delete=models.CASCADE
    )
    url = models.URLField(null=False, blank=False)
    created = models.DateTimeField(auto_now_add=True)
    was_received = models.BooleanField(
        default=True, null=False
    )  # did we sent it or did we receive it?

    class Meta:
        ordering = ["-created", "story"]

    def __str__(self):
        return f"{self.id} {self.story} {self.url}"
