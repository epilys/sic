from datetime import datetime, timedelta
import logging
import email
import re
import typing
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
        domain = f"{config.WEB_PROTOCOL}://{config.get_domain()}"
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
                            "List-ID": f"{config.verbose_name} digests <{config.NOTIFICATION_FROM}>",
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


def post_receive_job(job):
    return post_receive(job.data)


def post_receive(data: typing.Union[str, bytes], user=None) -> str:
    if isinstance(data, str):
        msg = email.message_from_string(data, policy=email_policy)
    else:
        msg = email.message_from_bytes(data, policy=email_policy)
    if not msg["message-id"]:
        raise Exception("Post has no Message-ID")

    # Check for duplicate posts
    if (
        Comment.objects.filter(message_id=msg["message-id"]).exists()
        or Story.objects.filter(message_id=msg["message-id"]).exists()
    ):
        raise Exception("Post with this Message-ID already exists.")
    dup_pk_search = PK_MSG_ID_RE.search(msg["message-id"])
    if dup_pk_search:
        exists = (
            Story.objects.filter(pk=dup_pk_search.group("story_pk")).exists()
            if dup_pk_search.group("story_pk")
            else Comment.objects.filter(pk=dup_pk_search.group("comment_pk")).exists()
        )
        if exists:
            raise Exception("Post with this Message-ID already exists.")

    is_from_mailing_list: bool = user is None
    if not user:
        if not msg["from"]:
            raise Exception("Post has no From")
        from_ = msg["from"].addresses[0].addr_spec
        user = User.objects.get(email=from_)
    body = msg.get_body(preferencelist=("markdown", "plain", "html"))  # type: ignore
    if body["content-type"] and body["content-type"].maintype != "text":
        raise Exception("Not text.")
    if body["content-type"] and body["content-type"].subtype == "html":
        text = Textractor.extract(body.get_content()).strip()
    else:
        text = body.get_content().strip()

    if not user.has_perm("sic.add_comment") or not user.has_perm("sic.add_story"):
        EmailMessage(
            f"[{config.verbose_name}] Your message has been rejected.",
            "You do not have permissions to post.",
            config.DEFAULT_FROM_EMAIL,
            [user.email],
            headers={"Message-ID": config.make_msgid()},
        ).send(fail_silently=False)
        raise Exception(f"{user} doesn't have permission to post")
    elif not user.enable_mailing_list_replying and is_from_mailing_list:
        EmailMessage(
            f"[{config.verbose_name}] Your message has been rejected.",
            "You have disabled posting via mailing list in your account settings.",
            config.DEFAULT_FROM_EMAIL,
            [user.email],
            headers={"Message-ID": config.make_msgid()},
        ).send(fail_silently=False)
        raise Exception(f"{user} doesn't have enable_mailing_list_replying")

    if "In-Reply-To" in msg or "References" in msg:
        # This is a comment
        if "In-Reply-To" in msg:
            in_reply_to = msg["In-Reply-To"].strip()
        else:
            in_reply_to = msg["References"].strip().split()[-1]
        in_reply_to_obj = None
        pk_search = PK_MSG_ID_RE.search(in_reply_to)
        in_reply_to_obj = Story.objects.filter(message_id=in_reply_to).first()
        if not in_reply_to_obj:
            in_reply_to_obj = Comment.objects.filter(message_id=in_reply_to).first()
        if not in_reply_to_obj:
            if pk_search:
                in_reply_to_obj = (
                    Story.objects.filter(pk=pk_search.group("story_pk")).first()
                    if pk_search.group("story_pk")
                    else Comment.objects.filter(
                        pk=pk_search.group("comment_pk")
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

    # Accept as story

    tags = []
    if "tags" in msg and msg["tags"]:
        tags = list(
            filter(
                lambda t: t is not None,
                map(
                    lambda t: Tag.objects.filter(name=t.strip()).first(),
                    msg["tags"].split(","),
                ),
            )
        )
    content_warning = None

    if "content-warning" in msg and msg["content-warning"]:
        content_warning = msg["content-warning"]

    url = None
    if "url" in msg and msg["url"]:
        url = msg["url"]

    publish_date = None
    if "publish-date" in msg and msg["publish-date"]:
        publish_date = msg["publish-date"]

    user_is_author = False

    if "user-is-author" in msg and msg["user-is-author"]:
        user_is_author = msg["user-is-author"].strip().casefold() in ["yes", "no"]

    description = text

    if not url and not description:
        raise Exception("A story must have a URL or a description.")

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
    story.tags.set(tags)
    story.save()
    return f"created story {story.pk}"


@receiver(post_save, sender=Story)
def story_create_mailing_list(
    sender, instance, created, raw, using, update_fields, **kwargs
):
    if not created or not instance.active or not config.MAILING_LIST:
        return
    story_obj = instance

    # Story has just been created. Tags are not available at this point, since
    # the story must be created before a story-tag relationship can be created.
    # So we can't send stories to subscribers yet. Schedule it as a job and
    # assume the correct tags will be available then.

    from sic.jobs import Job, JobKind

    kind = JobKind.from_func(create_story_post_on_mailing_list)
    _job_obj, _ = Job.objects.get_or_create(
        kind=kind, periodic=False, data=story_obj.pk
    )


def create_story_post_on_mailing_list(job):
    pk = job.data
    if isinstance(pk, str):
        pk = int(pk)
    story_obj = Story.objects.get(pk=pk)

    users = User.objects.filter(enable_mailing_list=True)

    if not users.exists():
        return "no users to send to"

    users = list(users)
    users_list: typing.List[User] = list(
        filter(lambda user: story_obj.is_user_subscribed(user), users)
    )
    if not users_list:
        return "no users to send to"

    headers: typing.Dict[str, str] = {
        "Message-ID": story_obj.get_message_id,
        "Archived-At": f"<{config.WEB_PROTOCOL}://{config.get_domain()}{story_obj.get_absolute_url()}>",
        "List-ID": f"{config.MAILING_LIST_ID} <{config.mailing_list_address()}>",
        "List-Unsubscribe": f"<{config.WEB_PROTOCOL}://{config.get_domain()}{reverse('edit_settings')}>",
        "Tags": ", ".join(map(lambda t: t.name, story_obj.tags.all())),
        "Reply-To": config.mailing_list_address(),
    }
    description = story_obj.description_to_plain_text
    if story_obj.url:
        description = f"{story_obj.url}\n\n{description}"

    with mail.get_connection(fail_silently=False) as connection:
        for user in users_list:
            EmailMessage(
                f"[{config.verbose_name}] {story_obj.title}",
                description,
                config.MAILING_LIST_FROM
                if config.MAILING_LIST_FROM
                else f""""{story_obj.user}" <{str(story_obj.user).replace(" ", ".")}@{config.get_domain()}>""",
                [user.email],
                headers=headers,
                connection=connection,
            ).send()
    return f"sent story to {len(users_list)} users"


@receiver(post_save, sender=Comment)
def comment_create_mailing_list(
    sender, instance, created, raw, using, update_fields, **kwargs
):
    if not created or instance.deleted or not config.MAILING_LIST:
        return
    comment_obj: Comment = instance
    story_obj: Story = comment_obj.story
    in_reply_to: str = story_obj.get_message_id
    users = User.objects.filter(
        enable_mailing_list=True, enable_mailing_list_comments=True
    )
    if comment_obj.parent:
        users = users.union(
            User.objects.filter(pk=comment_obj.parent.user_id).filter(
                enable_mailing_list_replies=True
            )
        )
        in_reply_to = comment_obj.parent.get_message_id
    if not users.exists():
        return

    users_list: typing.List[User] = list(
        filter(lambda user: story_obj.is_user_subscribed(user), users)
    )
    if not users_list:
        return

    references = []
    parent_ptr = comment_obj.parent
    while parent_ptr is not None:
        references.append(parent_ptr.get_message_id)
        parent_ptr = parent_ptr.parent
    references.append(story_obj.get_message_id)

    references_str = " ".join(reversed(references))

    headers: typing.Dict[str, str] = {
        "Message-ID": comment_obj.get_message_id,
        "Archived-At": f"<{config.WEB_PROTOCOL}://{config.get_domain()}{comment_obj.get_absolute_url()}>",
        "List-ID": f"{config.MAILING_LIST_ID} <{config.mailing_list_address()}>",
        "List-Unsubscribe": f"<{config.WEB_PROTOCOL}://{config.get_domain()}{reverse('edit_settings')}>",
        "Tags": ", ".join(map(lambda t: t.name, story_obj.tags.all())),
        "Reply-To": config.mailing_list_address(),
        "In-Reply-To": in_reply_to,
        "References": references_str,
    }
    with mail.get_connection(fail_silently=False) as connection:
        for user in users_list:
            EmailMessage(
                f"Re: [{config.verbose_name}] {story_obj.title}",
                comment_obj.text_to_plain_text,
                config.MAILING_LIST_FROM
                if config.MAILING_LIST_FROM
                else f""""{comment_obj.user}" <{str(comment_obj.user).replace(" ", ".")}@{config.get_domain()}>""",
                [user.email],
                headers=headers,
                connection=connection,
            ).send()


def story_as_email(pk):
    if isinstance(pk, str):
        pk = int(pk)
    story_obj = Story.objects.get(pk=pk)
    headers: typing.Dict[str, str] = {
        "To": config.mailing_list_address(),
        "Message-ID": story_obj.get_message_id,
        "Archived-At": f"<{config.WEB_PROTOCOL}://{config.get_domain()}{story_obj.get_absolute_url()}>",
        "List-ID": f"{config.MAILING_LIST_ID} <{config.mailing_list_address()}>",
        "List-Unsubscribe": f"<{config.WEB_PROTOCOL}://{config.get_domain()}{reverse('edit_settings')}>",
        "Tags": ", ".join(map(lambda t: t.name, story_obj.tags.all())),
        "Reply-To": config.mailing_list_address(),
    }
    description = story_obj.description_to_plain_text
    if story_obj.url:
        description = f"{story_obj.url}\n\n{description}"
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"] = f"[{config.verbose_name}] {story_obj.title}"
    msg["From"] = (
        config.MAILING_LIST_FROM
        if config.MAILING_LIST_FROM
        else f""""{story_obj.user}" <{str(story_obj.user).replace(" ", ".")}@{config.get_domain()}>"""
    )
    for (k, v) in headers.items():
        msg[k] = v
    msg.set_content(description)
    return str(msg)


def comment_as_email(pk):
    if isinstance(pk, str):
        pk = int(pk)
    comment_obj = Comment.objects.get(pk=pk)
    story_obj: Story = comment_obj.story
    in_reply_to: str = story_obj.get_message_id
    if comment_obj.parent:
        in_reply_to = comment_obj.parent.get_message_id

    references = []
    parent_ptr = comment_obj.parent
    while parent_ptr is not None:
        references.append(parent_ptr.get_message_id)
        parent_ptr = parent_ptr.parent
    references.append(story_obj.get_message_id)

    references_str = " ".join(reversed(references))

    headers: typing.Dict[str, str] = {
        "To": config.mailing_list_address(),
        "Message-ID": comment_obj.get_message_id,
        "Archived-At": f"<{config.WEB_PROTOCOL}://{config.get_domain()}{comment_obj.get_absolute_url()}>",
        "List-ID": f"{config.MAILING_LIST_ID} <{config.mailing_list_address()}>",
        "List-Unsubscribe": f"<{config.WEB_PROTOCOL}://{config.get_domain()}{reverse('edit_settings')}>",
        "Tags": ", ".join(map(lambda t: t.name, story_obj.tags.all())),
        "Reply-To": config.mailing_list_address(),
        "In-Reply-To": in_reply_to,
        "References": references_str,
    }
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"] = f"Re: [{config.verbose_name}] {story_obj.title}"
    msg["From"] = (
        config.MAILING_LIST_FROM
        if config.MAILING_LIST_FROM
        else f""""{comment_obj.user}" <{str(comment_obj.user).replace(" ", ".")}@{config.get_domain()}>"""
    )

    for (k, v) in headers.items():
        msg[k] = v
    msg.set_content(comment_obj.text_to_plain_text)
    return str(msg)
