from urllib.parse import urlparse, unquote_plus, quote_plus
from datetime import datetime, timedelta
import string
import uuid
import abc
from django.db import models, connection, migrations
from django.db.models.expressions import RawSQL
from django.contrib.auth.models import (
    BaseUserManager,
    AbstractBaseUser,
    PermissionsMixin,
)
from django.contrib.contenttypes.models import ContentType
from django.contrib import messages
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.timezone import make_aware
from django.utils.functional import cached_property
from django.core.cache import cache
from django.core.mail import EmailMessage
from django.contrib.sites.shortcuts import get_current_site
from django.contrib.sites.models import Site
from django.conf import settings
from django.dispatch import receiver
from django.db.backends.signals import connection_created
from django.core.exceptions import ValidationError
from django.core.validators import MinLengthValidator


from .apps import SicAppConfig as config
from .markdown import comment_to_html, Textractor
from .voting import story_hotness

url_decode_translation = str.maketrans(string.ascii_lowercase[:10], string.digits)
url_encode_translation = str.maketrans(string.digits, string.ascii_lowercase[:10])


class Domain(models.Model):
    url = models.URLField(
        null=False, blank=False, primary_key=True, validators=[MinLengthValidator(5)]
    )

    def save(self, *args, **kwargs):
        if len(self.url) == 0:
            raise ValidationError("Domain can't be empty.")
        try:
            netloc = urlparse(self.url).netloc
            if netloc.startswith("www."):
                netloc = netloc[4:]
            if len(netloc) > 0:
                if netloc != self.url and Domain.objects.filter(url=netloc).exists():
                    raise ValidationError(f"Domain already exists as {netloc}.")
                self.url = netloc
        except:
            pass
        super().save(*args, **kwargs)

    def __str__(self):
        return self.url

    @cached_property
    def slugify(self):
        return quote_plus(self.url)

    @staticmethod
    def deslugify(slug):
        return unquote_plus(slug)

    def get_absolute_url(self):
        return reverse(
            "domain",
            args=[self.slugify],
        )


class StoryKind(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(null=False, blank=False, max_length=40, unique=True)
    hex_color = models.CharField(max_length=7, null=True, blank=True, default="#fffff")
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name}"

    def color_vars_css(self):
        hex_ = self.hex_color.lstrip("#")
        red, green, blue = tuple(int(hex_[i : i + 2], 16) for i in (0, 2, 4))
        return f"--red: {red}; --green:{green}; --blue:{blue};"

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
    domain = models.ForeignKey(
        Domain, on_delete=models.SET_NULL, null=True, default=None, blank=True
    )
    created = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now_add=True)
    last_active = models.DateTimeField(auto_now_add=True, null=False)
    publish_date = models.DateField(null=True, blank=True)

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
    context_warning = models.CharField(null=True, blank=False, max_length=30)

    class Meta:
        verbose_name_plural = "stories"

    def __str__(self):
        return f"{self.title}"

    @cached_property
    def slugify(self):
        return slugify(self.title, allow_unicode=True)

    def get_absolute_url(self):

        return reverse(
            "story",
            kwargs={"story_pk": self.pk, "slug": self.slugify},
        )

    @cached_property
    def karma(self):
        return self.votes.filter(comment=None).count()

    @cached_property
    def get_listing_url(self):
        return (
            self.get_absolute_url()
            if self.url is None or len(self.url) == 0
            else self.url
        )

    @cached_property
    def get_domain(self):
        if not self.url or len(self.url) == 0:
            return None
        if self.domain_id is None:
            self.save()
        return self.domain

    @cached_property
    def hotness(self):
        return story_hotness(self)

    @cached_property
    def description_to_html(self):
        return comment_to_html(self.description)

    @cached_property
    def description_to_plain_text(self):
        return Textractor.extract(self.description_to_html).strip()

    @cached_property
    def active_comments(self):
        return self.comments.filter(deleted=False)

    def save(self, *args, **kwargs):
        netloc = urlparse(self.url).netloc
        if netloc.startswith("www."):
            netloc = netloc[4:]
        if len(netloc) > 0:
            domain_obj, _ = Domain.objects.get_or_create(url=netloc)
            self.domain = domain_obj
        super().save(*args, **kwargs)


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
    last_modified = models.DateTimeField(auto_now_add=True)
    text = models.TextField(null=True, blank=False)

    def __str__(self):
        return f"{self.user} {self.created}"

    def last_log_entry(self):
        from .moderation import ModerationLogEntry

        entry = ModerationLogEntry.objects.filter(
            object_id=self.id,
            content_type=ContentType.objects.get(app_label="sic", model="comment"),
        ).latest("action_time")

        return entry

    def get_absolute_url(self):
        return self.story.get_absolute_url() + f"#{self.slugify}"

    @cached_property
    def slugify(self) -> str:
        return str(self.id).translate(url_encode_translation)

    @staticmethod
    def deslugify(slug: str):
        return int(slug.translate(url_decode_translation))

    @cached_property
    def karma(self):
        return self.votes.count()

    @cached_property
    def text_to_html(self):
        return comment_to_html(self.text)

    @cached_property
    def text_to_plain_text(self):
        return Textractor.extract(self.text_to_html).strip()


class Tag(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(null=False, blank=False, max_length=40, unique=True)
    hex_color = models.CharField(max_length=7, null=True, blank=True, default="#ffffff")
    created = models.DateTimeField(auto_now_add=True)
    parents = models.ManyToManyField("Tag", related_name="children", blank=True)

    def __str__(self):
        return f"{self.name}"

    def color_vars_css(self):
        hex_ = self.hex_color.lstrip("#")
        red, green, blue = tuple(int(hex_[i : i + 2], 16) for i in (0, 2, 4))
        return f"--red: {red}; --green:{green}; --blue:{blue};"

    def in_taggregations(self):
        return Taggregation.objects.filter(
            id__in=RawSQL(
                "SELECT DISTINCT taggregation_id AS id FROM taggregation_tags WHERE tag_id = %s",
                [self.pk],
            ),
            private=False,
        )

    def get_stories(self, depth=0):
        if depth is None:
            return Story.objects.filter(
                tags__pk__in=RawSQL(
                    """WITH RECURSIVE w (
    root_tag_id,
    tag_id,
    depth
) AS (
    SELECT DISTINCT
        id,
        id,
        0
    FROM
        sic_tag
    UNION ALL
    SELECT
        w.root_tag_id,
        p.from_tag_id,
        w.depth + 1
    FROM
        sic_tag_parents AS p
        JOIN w ON w.tag_id = p.to_tag_id
) SELECT DISTINCT
    tag_id
FROM
    w
WHERE
    root_tag_id = %s""",
                    [self.pk],
                )
            )
        return Story.objects.filter(
            tags__pk__in=RawSQL(
                """WITH RECURSIVE w (
    root_tag_id,
    tag_id,
    depth
) AS (
    SELECT DISTINCT
        id,
        id,
        0
    FROM
        sic_tag
    UNION ALL
    SELECT
        w.root_tag_id,
        p.from_tag_id,
        w.depth + 1
    FROM
        sic_tag_parents AS p
        JOIN w ON w.tag_id = p.to_tag_id
) SELECT DISTINCT
    tag_id
FROM
    w
WHERE
    root_tag_id = %s AND
    depth <= %s""",
                [self.pk, depth],
            )
        )

    @cached_property
    def slugify(self):
        return slugify(self.name, allow_unicode=True)

    def hotness_modifier(self):
        return 0.0

    @cached_property
    def latest(self):
        stories = self.get_stories(-1)
        if stories.exists():
            return stories.latest("created")
        return None

    def get_absolute_url(self):
        return reverse(
            "view_tag",
            kwargs={"tag_pk": self.pk, "slug": self.slugify},
        )

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

    @cached_property
    def slugify(self):
        return slugify(self.name, allow_unicode=True)

    def get_absolute_url(self):
        return reverse(
            "taggregation",
            kwargs={"taggregation_pk": self.pk, "slug": self.slugify},
        )

    def user_has_access(self, user):
        if user.is_authenticated:
            return (not self.private) or (
                (user.pk == self.creator.pk) or (user in self.moderators.all())
            )
        return not self.private

    def user_can_modify(self, user):
        if not self.user_has_access(user):
            return False
        return (user.pk == self.creator.pk) or (user in self.moderators.all())

    def get_stories(self):
        # TODO: This generates a SELECT .. IN (SELECT DISTINCT ...) which definitely can be improved
        return Story.objects.filter(
            id__in=RawSQL(
                "SELECT DISTINCT s.id AS id FROM sic_story AS s JOIN sic_story_tags AS t ON t.story_id = s.id JOIN taggregation_tags AS v ON v.tag_id = t.tag_id WHERE v.taggregation_id = %s",
                [self.pk],
            )
        )

    @cached_property
    def vertices(self):
        return Tag.objects.filter(
            id__in=RawSQL(
                "SELECT DISTINCT tag_id AS id FROM taggregation_tags WHERE taggregation_id = %s",
                [self.pk],
            )
        )

    @staticmethod
    def default_frontpage():
        taggregations = Taggregation.objects.filter(default=True)
        if not taggregations.exists():
            return {
                "stories": Story.objects.filter(active=True),
                "taggregations": Taggregation.objects.none(),
            }

        # Perform raw query directly instead of UNIONing all taggregation frontpages
        stories = Story.objects.filter(
            id__in=RawSQL(
                "SELECT DISTINCT s.id AS id FROM sic_story AS s JOIN sic_story_tags AS t ON t.story_id = s.id JOIN taggregation_tags AS v ON v.tag_id = t.tag_id JOIN sic_taggregation as agg ON v.taggregation_id = agg.id WHERE agg.'default' = 1",
                [],
            )
        )
        return {
            "stories": stories,
            "taggregations": taggregations,
        }

    def last_active(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT last_active FROM taggregation_last_active WHERE taggregation_id = %s",
                [self.pk],
            )
            last_active = cursor.fetchone()
        return (
            make_aware(datetime.fromisoformat(last_active[0]))
            if (last_active and last_active[0])
            else None
        )

    @staticmethod
    def last_actives(taggregations):
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT MAX(last_active) FROM taggregation_last_active WHERE taggregation_id IN ({','.join([str(t.pk) for t in taggregations])})",
                [],
            )
            last_active = cursor.fetchone()
        return (
            make_aware(datetime.fromisoformat(last_active[0]))
            if (last_active and last_active[0])
            else None
        )

    def last_14_days(self):
        key = f"last_14_days_{self.pk}"
        cached_sparkline = cache.get(key)
        if cached_sparkline is None:
            # Unicode: 9601, 9602, 9603, 9604, 9605, 9606, 9607, 9608
            # bar = "▁▂▃▄▅▆▇█"
            bar = "▂▃▅▆▇"
            barcount = len(bar)

            def sparkline(numbers):
                mn, mx = min(numbers), max(numbers)
                extent = mx - mn
                sparkline = "".join(
                    bar[min([barcount - 1, int((n - mn) / extent * barcount)])]
                    for n in numbers
                )
                return mn, mx, sparkline

            d = timezone.now().date() - timedelta(days=14)
            days = [0] * 15
            total = 0
            for delta in map(
                lambda story: story.created.date() - d,
                self.get_stories().filter(created__gt=d),
            ):
                days[delta.days] += 1
                total += 1
            if total != 0:
                cached_sparkline = sparkline(days)
            else:
                cached_sparkline = (0, 0, bar[0] * 14)
            cache.set(key, cached_sparkline, timeout=60 * 60 * 4)
        return cached_sparkline[2]

    class Meta:
        ordering = ["name"]


class TaggregationHasTag(models.Model):
    id = models.AutoField(primary_key=True)
    taggregation = models.ForeignKey(Taggregation, on_delete=models.CASCADE)
    tag = models.ForeignKey(Tag, null=True, blank=True, on_delete=models.CASCADE)
    depth = models.PositiveIntegerField(default=0, null=True, blank=True)
    exclude_filters = models.ManyToManyField(
        "StoryFilter", blank=True, related_name="excluded_in"
    )

    def __str__(self):
        return f"{self.taggregation} {self.tag} depth={self.depth}"

    @cached_property
    def vertices(self):
        return Tag.objects.filter(
            id__in=RawSQL(
                "SELECT DISTINCT tag_id AS id FROM taggregation_tags WHERE taggregationhastag_id = %s",
                [self.pk],
            )
        )

    def get_stories(self):
        return Story.objects.filter(
            id__in=RawSQL(
                "SELECT DISTINCT s.id AS id FROM sic_story AS s JOIN sic_story_tags AS t ON t.story_id = s.id JOIN taggregation_tags AS v ON v.tag_id = t.tag_id WHERE v.taggregationhastag_id = %s",
                [self.pk],
            )
        )


class StoryFilter(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(null=False, blank=True, max_length=20)

    def __str__(self) -> str:
        return self.name if len(self.name) > 0 else "unnamed"

    @abc.abstractmethod
    def kind(self):
        ...

    @abc.abstractmethod
    def content(self):
        ...

    # def into_inner(self):
    #    try:
    #        return self.exacttagfilter
    #    except:
    #        pass
    #    try:
    #        return self.nametagfilter
    #    except:
    #        pass
    #    try:
    #        return self.domaintagfilter
    #    except:
    #        pass
    #    try:
    #        return self.userfilter
    #    except:
    #        pass
    #    return None

    @staticmethod
    def filter_filters(filters):
        tag_filters = []
        domain_filters = []
        user_filters = []
        for filter_ in filters:
            filter_ = filter_.inner()
            if isinstance(filter_, (TagNameFilter, ExactTagFilter)):
                tag_filters.append(filter_)
            elif isinstance(filter_, DomainFilter):
                domain_filters.append(filter_)
            elif isinstance(filter_, UserFilter):
                user_filters.append(filter_)
        return {
            "tag_filters": tag_filters,
            "user_filters": user_filters,
            "domain_filters": domain_filters,
        }


class MatchFilter(StoryFilter):
    match_string = models.TextField(null=False, blank=False)
    is_regexp = models.BooleanField(null=False, blank=False, default=False)

    def content(self):
        return self.match_string

    def kind(self):
        return "match filter"


class ExactTagFilter(StoryFilter):
    tag = models.ForeignKey(Tag, null=False, blank=True, on_delete=models.CASCADE)

    def content(self):
        return self.tag

    def kind(self):
        return "exact tag filter"

    def match(self):
        return lambda tag_obj: tag_obj.pk == self.tag.pk


class TagNameFilter(MatchFilter):
    def kind(self):
        return "tag name match filter"

    def content(self):
        return self.match_string

    def match(self):
        if self.is_regexp:
            raise NotImplementedError(
                "regular expression matching in story filters not implemented yet"
            )
        return lambda tag_obj: self.match_string in tag_obj.name


class DomainFilter(MatchFilter):
    def kind(self):
        return "domain match filter"

    def content(self):
        return self.match_string

    def match(self):
        if self.is_regexp:
            raise NotImplementedError(
                "regular expression matching in story filters not implemented yet"
            )
        return lambda domain_obj: self.match_string in domain_obj


class UserFilter(StoryFilter):
    user = models.ForeignKey("User", on_delete=models.CASCADE, null=False)

    def kind(self):
        return "user filter"

    def content(self):
        return self.user

    def match(self):
        return lambda user_obj: user_obj.pk == self.user.pk


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
    show_stories_with_context_warning = models.BooleanField(default=True, null=False)

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

    @cached_property
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
        return self.notifications.filter(read__isnull=True).order_by("-created")

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
            # Perform raw query directly instead of UNIONing all taggregation frontpages
            stories = Story.objects.filter(
                id__in=RawSQL(
                    "SELECT DISTINCT s.id AS id FROM sic_story AS s JOIN sic_story_tags AS t ON t.story_id = s.id JOIN taggregation_tags AS v ON v.tag_id = t.tag_id JOIN sic_user_taggregation_subscriptions as subs WHERE v.taggregation_id = subs.taggregation_id AND subs.user_id = %s",
                    [self.pk],
                )
            )
            taggregations = self.taggregation_subscriptions.all()
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
    last_modified = models.DateTimeField(auto_now_add=True)
    annotation = models.TextField(null=True, blank=True)

    class Meta:
        unique_together = ["comment", "user"]


class StoryBookmark(models.Model):
    id = models.AutoField(primary_key=True)
    story = models.ForeignKey(Story, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created = models.DateTimeField(auto_now_add=True)
    last_modified = models.DateTimeField(auto_now_add=True)
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
    read = models.DateTimeField(default=None, null=True)
    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} {self.kind}"

    def send(self, request=None):
        if request:
            domain = get_current_site(request).domain
        else:
            domain = Site.objects.get_current().domain
        root_url = f"http://{domain}" if settings.DEBUG else f"https://{domain}"
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

    @staticmethod
    def latest(user):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT MAX(MAX(created), MAX(read)) FROM sic_notification WHERE user_id = %s;",
                [user.pk],
            )
            latest = cursor.fetchone()
        return (
            make_aware(datetime.fromisoformat(latest[0]))
            if (latest and latest[0])
            else None
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


@receiver(connection_created)
def taggregation_queries_setup(sender, connection, **kwargs):
    if getattr(migrations, "MIGRATION_OPERATION_IN_PROGRESS", False):
        return
    with connection.cursor() as cursor:
        cursor.execute(
            """CREATE TEMPORARY VIEW taggregationhastag_exacttag AS
SELECT
    tag_id,
    exclude_filter.taggregationhastag_id AS taggregationhastag_id
FROM
    sic_taggregationhastag_exclude_filters AS exclude_filter,
    sic_exacttagfilter AS exact_tag
WHERE
    exclude_filter.storyfilter_id = exact_tag.storyfilter_ptr_id;"""
        )

        cursor.execute(
            """CREATE TEMPORARY VIEW taggregation_tags AS WITH RECURSIVE w (
    taggregation_id,
    tag_id,
    depth,
    taggregationhastag_id
) AS (
    SELECT DISTINCT
        taggregation_id,
        tag_id,
        depth,
        id
    FROM
        sic_taggregationhastag
    UNION ALL
    SELECT
        w.taggregation_id AS taggregation_id,
        p.from_tag_id AS tag_id,
        (
            CASE w.depth
            WHEN NULL THEN
                w.depth
            ELSE
                w.depth - 1
            END),
        taggregationhastag_id
    FROM
        sic_tag_parents AS p
        JOIN w ON w.tag_id = p.to_tag_id
    WHERE
        (w.depth != 0 OR w.depth ISNULL)
        AND p.from_tag_id NOT IN (
            SELECT
                tag_id
            FROM
                taggregationhastag_exacttag)
) SELECT DISTINCT
    taggregation_id,
    tag_id,
    depth,
    taggregationhastag_id
FROM
    w;"""
        )

        cursor.execute(
            """CREATE TEMPORARY VIEW taggregationhastag_userfilter AS
SELECT
    user_id,
    exclude_filter.taggregationhastag_id AS taggregationhastag_id
FROM
    sic_taggregationhastag_exclude_filters AS exclude_filter,
    sic_userfilter AS userfilter
WHERE
    exclude_filter.storyfilter_id = userfilter.storyfilter_ptr_id;"""
        )

        cursor.execute(
            """CREATE TEMPORARY VIEW taggregationhastag_domainfilter AS
SELECT
    match_string,
    is_regexp,
    exclude_filter.taggregationhastag_id AS taggregationhastag_id
FROM
    sic_taggregationhastag_exclude_filters AS exclude_filter,
    sic_matchfilter AS matchfilter,
    sic_domainfilter AS domainfilter
WHERE
    exclude_filter.storyfilter_id = matchfilter.storyfilter_ptr_id;"""
        )


@receiver(connection_created)
def last_modified_triggers(sender, connection, **kwargs):
    if getattr(migrations, "MIGRATION_OPERATION_IN_PROGRESS", False):
        return
    with connection.cursor() as cursor:
        cursor.execute(
            """CREATE TEMPORARY TRIGGER IF NOT EXISTS update_last_modified_aggregation AFTER UPDATE OF name, description, 'default', discoverable, private ON sic_taggregation FOR EACH ROW
BEGIN
    UPDATE sic_taggregation
    SET last_modified = strftime('%Y-%m-%d %H:%M:%f000', 'now')
WHERE
    id = NEW.id;
END;"""
        )
        cursor.execute(
            """CREATE TEMPORARY TRIGGER IF NOT EXISTS update_last_modified_story_on_insert_comment AFTER INSERT ON sic_comment FOR EACH ROW
BEGIN
    UPDATE sic_story
    SET last_active = NEW.last_modified
WHERE
    id = NEW.story_id;
END;"""
        )
        cursor.execute(
            """CREATE TEMPORARY TRIGGER IF NOT EXISTS update_last_modified_story_on_update_comment AFTER UPDATE OF last_modified ON sic_comment FOR EACH ROW
BEGIN
    UPDATE sic_story
    SET last_active = NEW.last_modified
WHERE
    id = NEW.story_id;
END;"""
        )
        cursor.execute(
            """CREATE TEMPORARY TRIGGER IF NOT EXISTS update_last_modified_story_on_delete_comment AFTER DELETE ON sic_comment FOR EACH ROW
BEGIN
    UPDATE sic_story
    SET last_active = strftime('%Y-%m-%d %H:%M:%f000', 'now')
WHERE
    id = OLD.story_id;
END;"""
        )
        cursor.execute(
            """CREATE TEMPORARY TRIGGER IF NOT EXISTS update_last_modified_story_on_insert_vote AFTER INSERT ON sic_vote FOR EACH ROW
BEGIN
    UPDATE sic_story
    SET last_active = NEW.created
WHERE
    id = NEW.story_id;
END;"""
        )
        cursor.execute(
            """CREATE TEMPORARY TRIGGER IF NOT EXISTS update_last_modified_story_on_update_vote AFTER UPDATE ON sic_vote FOR EACH ROW
BEGIN
    UPDATE sic_story
    SET last_active = strftime('%Y-%m-%d %H:%M:%f000', 'now')
WHERE
    id = NEW.story_id;
END;"""
        )
        cursor.execute(
            """CREATE TEMPORARY TRIGGER IF NOT EXISTS update_last_modified_story_on_delete_vote AFTER DELETE ON sic_vote FOR EACH ROW
BEGIN
    UPDATE sic_story
    SET last_active = strftime ('%Y-%m-%d %H:%M:%f000', 'now')
WHERE
    id = OLD.story_id;
END;"""
        )
        cursor.execute(
            """CREATE TEMPORARY VIEW taggregation_last_active AS
SELECT
    MAX(s.last_active) AS last_active,
    v.taggregation_id AS taggregation_id
FROM
    sic_story AS s
    JOIN sic_story_tags AS t ON t.story_id = s.id
    JOIN taggregation_tags AS v ON v.tag_id = t.tag_id
GROUP BY
    taggregation_id;"""
        )


class StoryRemoteContent(models.Model):
    story = models.OneToOneField(
        "Story",
        related_name="remote_content",
        on_delete=models.CASCADE,
        null=False,
        unique=True,
        primary_key=True,
    )
    url = models.URLField(null=False, blank=False)
    content = models.TextField(null=False, blank=False)
    retrieved_at = models.DateTimeField(null=False, blank=False, auto_now_add=True)

    def __str__(self):
        return f"{self.story} {self.url} {len(self.content)} bytes"
