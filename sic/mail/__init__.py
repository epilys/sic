from datetime import datetime, timedelta
import logging
import email
import itertools
import re
from email.policy import default as email_policy
from django.db import models
from django.db.models import F, Q
from django.template import Context, Template
from django.core import mail
from django.utils.timezone import make_aware
from django.core.mail import EmailMessage
from django.urls import reverse
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.mail import EmailMessage
from django.apps import apps

config = apps.get_app_config("sic")
from sic.models import Story, User, Comment, Tag, ExactTagFilter, DomainFilter
from sic.markdown import Textractor

logger = logging.getLogger("sic")


def test_bit(int_, offset):
    mask = 1 << offset
    return int_ & mask > 0


def set_bit(int_, offset):
    mask = 1 << offset
    return int_ | mask


def clear_bit(int_, offset):
    mask = ~(1 << offset)
    return int_ & mask


DIGEST_TEMPLATE = """To stop receiving these messages, visit your account settings and turn digests off: {{ unsubscribe }}

{% if aggregations %}Stories from {% for agg in aggregations %}{{ agg.name }}{% if not forloop.last %}, {% endif %}{% endfor %}{% else %}Stories from all tags{% endif %}:
{% for story in stories %}
- {{ story.title }} | {{ story.url }}{% if story.publish_date %} Published on {{ story.publish_date }}{% endif %} Tags: {% for tag in story.tags.all %}{% if forloop.first %}({% endif %}{{ tag }}{% if not forloop.last %}, {% else %}){% endif %}{% empty %}none{% endfor %}
  Comments: {{ domain }}{{ story.get_absolute_url }} | {{ story.created }}
  {% endfor %}"""


class Digest(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(
        "User",
        related_name="email_digest",
        unique=True,
        on_delete=models.CASCADE,
        null=False,
    )
    active = models.BooleanField(default=False, null=False)
    all_stories = models.BooleanField(default=True, null=False)
    on_days = models.SmallIntegerField(default=set_bit(0, 6), null=False, blank=False)
    last_run = models.DateTimeField(default=None, null=True, blank=True)

    @staticmethod
    def send_digests():
        today = datetime.now()
        day = today.isoweekday() - 1
        digests = Digest.objects.annotate(
            is_today=F("on_days").bitand(1 << day)
        ).filter(active=True, is_today__gt=0)
        if not digests.exists():
            return
        template = Template(DIGEST_TEMPLATE)
        domain = f"http://{config.get_domain()}"
        unsubscribe = f"{domain}{reverse('edit_settings')}"
        with mail.get_connection(fail_silently=False) as connection:
            for d in digests:
                aggregations = None
                if d.all_stories:
                    stories = Story.objects.filter(active=True)
                else:
                    frontpage = d.user.frontpage()
                    stories = frontpage["stories"]
                    aggregations = frontpage["taggregations"]
                if d.last_run:
                    stories = stories.filter(created__gt=d.last_run)
                else:
                    stories = stories.filter(
                        created__gt=make_aware(today - timedelta(days=32))
                    )
                stories = stories.exclude(user_id=d.user.id).order_by(
                    "-created", "title"
                )
                if not stories.exists():
                    d.last_run = make_aware(today)
                    d.save(update_fields=["last_run"])
                    continue
                context = Context(
                    {
                        "stories": stories,
                        "aggregations": aggregations,
                        "domain": domain,
                        "unsubscribe": unsubscribe,
                    }
                )
                try:
                    if d.user.username:
                        username = d.user.username.replace('"', "")
                        to = f""""{username}" <{d.user.email}>"""
                    else:
                        to = d.user.email
                    EmailMessage(
                        f"{config.DIGEST_SUBJECT} {today.date()}",
                        template.render(context),
                        config.NOTIFICATION_FROM,
                        [to],
                        headers={
                            "Message-ID": config.make_msgid(),
                            "List-ID": f"sic digests <{config.NOTIFICATION_FROM}>",
                            "List-Unsubscribe": f"<{unsubscribe}>",
                        },
                        connection=connection,
                    ).send()
                    d.last_run = make_aware(today)
                    d.save(update_fields=["last_run"])
                except Exception as exc:
                    logger.exception(exc)

    def set_day(self, day: int, value: bool):
        if value:
            self.on_days = set_bit(self.on_days, day)
        else:
            self.on_days = clear_bit(self.on_days, day)
        self.save(update_fields=["on_days"])

    @property
    def days(self):
        return list(
            map(
                lambda d: d[1],
                filter(
                    lambda d: test_bit(self.on_days, d[0]),
                    enumerate(
                        [
                            "Monday",
                            "Tuesday",
                            "Wednesday",
                            "Thursday",
                            "Friday",
                            "Saturday",
                            "Sunday",
                        ]
                    ),
                ),
            )
        )

    @property
    def days_list(self):
        return [test_bit(self.on_days, d) for d in range(0, 7)]


MSG_ID_RE = re.compile(r"^\s*<(?P<msg_id>[^>]+)>\s*")
PK_MSG_ID_RE = re.compile(
    r"(?:story-(?P<story_pk>\d+))|(?:comment-(?P<comment_pk>\d+))"
)
METADATA_RE = re.compile(
    r"(?:(?:url:\s*(?P<url>.+?)(?:\n|$))|(?:content-warning:\s*(?P<content_warning>.+?)(?:\n|$))|(?:tags:\s*(?P<tags>.+?)(?:\n|$))|(?:author:\s*(?P<author>.+?)(?:\n|$))|(?:publish-date:\s*(?P<publish_date>.+?)(?:\n|$)))+(?:\n(?P<description>(?:.|\n)*))?$",
    re.IGNORECASE,
)


def post_receive(data):
    msg = email.message_from_string(data, policy=email_policy)
    from_ = msg["from"].addresses[0].addr_spec
    user = User.objects.get(email=from_)
    body = msg.get_body(preferencelist=("markdown", "plain", "html"))
    if body["content-type"].maintype != "text":
        raise Exception("Not text.")
    if body["content-type"].subtype == "html":
        text = Textractor.extract(body.get_content()).strip()
    else:
        text = body.get_content().strip()
    if "In-Reply-To" in msg or "References" in msg:
        # This is a comment
        in_reply_to = msg["In-Reply-To"].strip()
        in_reply_to_obj = None
        pk_search = PK_MSG_ID_RE.search(in_reply_to)
        in_reply_to_obj = Story.objects.filter(message_id=in_reply_to).first()
        if not in_reply_to_obj:
            in_reply_to_obj = Comment.objects.filter(message_id=in_reply_to).first()
        if not in_reply_to_obj:
            if pk_search:
                in_reply_to_obj = (
                    Story.objects.filter(pk=pk_search.groups["story_pk"]).first()
                    if pk_search.groups["story_pk"]
                    else Comment.objects.filter(
                        pk=pk_search.groups["comment_pk"]
                    ).first()
                )
        if not in_reply_to_obj:
            raise Exception("In reply to what?")
        if isinstance(in_reply_to_obj, Comment):
            parent_id = in_reply_to_obj.id
            story_id = in_reply_to_obj.story_id
        else:
            parent_id = None
            story_id = in_reply_to_obj.id
        comment = Comment.objects.create(
            user=user,
            story_id=story_id,
            parent_id=parent_id,
            text=text,
            message_id=msg["message-id"],
        )
        return f"created comment {comment.pk}"

    metadata_search = METADATA_RE.search(text)
    if metadata_search:
        text = metadata_search.groups("description")
        publish_date = metadata_search.groups("publish_date")
        try:
            publish_date = (
                datetime.date.fromisoformat(publish_date.strip())
                if publish_date
                else None
            )
        except:
            publish_date = None
        url = metadata_search.groups("url")
        content_warning = metadata_search.groups("content_warning")
        author = (
            metadata_search.groups("author").lowercase()
            if metadata_search.groups("author")
            else None
        )
        user_is_author = author in ["yes", "true"] if author else False
        tags = metadata_search.groups("tags")
        if tags:
            tags = list(
                filter(
                    lambda t: Tag.objects.filter(name=t.strip()).first(),
                    tags.split(","),
                )
            )
    else:
        url = None
        publish_date = None
        description = text
        user_is_author = False
        content_warning = None
    # This is a story
    story = Story.objects.create(
        title=msg["subject"].strip(),
        url=url,
        publish_date=publish_date,
        description=description,
        user_id=user.id,
        user_is_author=user_is_author,
        content_warning=content_warning,
        message_id=msg["message-id"],
    )
    return f"created story {story.pk}"


@receiver(post_save, sender=Story)
def story_create_mailing_list(
    sender, instance, created, raw, using, update_fields, **kwargs
):
    if (not created and not instance.active) or not config.MAILING_LIST:
        return
    story_obj = instance
    users = User.objects.filter(enable_mailing_list=True)
    if not users.exists():
        return
    tags = story_obj.tags.all()
    message_id = story_obj.message_id
    if not message_id:
        message_id = f"<story-{story_obj.pk}@{config.get_domain()}>"
    any_matches = False
    for user in users:
        qobj = ~Q(story__pk=None)
        for f in ExactTagFilter.objects.filter(excluded_in_user=user):
            qobj |= f.as_q()
        for f in DomainFilter.objects.filter(excluded_in_user=user):
            qobj |= f.as_q()
        if not Story.objects.filter(pk=story_obj.pk).exclude(qobj).exists():
            continue
        match = False
        for has in itertools.chain.from_iterable(
            map(
                lambda sub: sub.taggregationhastag_set.all(),
                user.taggregation_subscriptions.all(),
            )
        ):
            if has.tag not in tags:
                continue
            has_match = True
            qobj = ~Q(story__pk=None)
            for f in filter(lambda f: f.into_inner(), has.exclude_filters.all()):
                qobj |= f.as_q()
            has_match = Story.objects.filter(pk=story_obj.pk).exclude(qobj).exists()
            match |= has_match
        if not match:
            continue
        any_matches = True
        EmailMessage(
            f"[sic] {story_obj.title}",
            story_obj.url if story_obj.url else story_obj.description,
            config.NOTIFICATION_FROM,
            [user.email],
            headers={"Message-ID": message_id},
        ).send(fail_silently=False)
    if any_matches and not story_obj.message_id:
        story_obj.message_id = message_id
        story_obj.save(update_fields=["message_id"])
