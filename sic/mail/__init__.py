from django.db import models
from django.db.models import F
from django.template import Context, Template
from django.core import mail
from django.utils.timezone import make_aware
from django.core.mail import EmailMessage
from django.urls import reverse
from ..apps import SicAppConfig as config
from ..models import Story
from datetime import datetime, timedelta
import logging

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
        messages = []
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
                stories = stories.order_by("-created", "title")
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
