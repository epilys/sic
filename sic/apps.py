from django.apps import AppConfig
from django.conf import settings
from functools import lru_cache
from email.utils import make_msgid


class SicAppConfig(AppConfig):
    name = "sic"
    verbose_name = "sic"

    BANNED_USERNAMES = [
        "admin",
        "administrator",
        "contact",
        "fraud",
        "guest",
        "help",
        "hostmaster",
        "sic",
        "Cher",
        "mailer-daemon",
        "moderator",
        "moderators",
        "nobody",
        "postmaster",
        "root",
        "security",
        "support",
        "sysop",
        "webmaster",
        "enable",
        "new",
        "signup",
    ]

    # days old accounts are considered new for
    NEW_USER_DAYS = 70

    # minimum karma required to be able to offer title/tag suggestions
    MIN_KARMA_TO_SUGGEST = 10

    # minimum karma required to be able to flag comments
    MIN_KARMA_TO_FLAG = 50

    # minimum karma required to be able to downvote
    MIN_KARMA_TO_DOWNVOTE = 10

    # minimum karma required to be able to submit new stories
    MIN_KARMA_TO_SUBMIT_STORIES = 0

    # minimum karma required to process invitation requests
    MIN_KARMA_FOR_INVITATION_REQUESTS = MIN_KARMA_TO_FLAG

    # proportion of posts authored by user to consider as heavy self promoter
    HEAVY_SELF_PROMOTER_PROPORTION = 0.51

    # minimum number of submitted stories before checking self promotion
    MIN_STORIES_CHECK_SELF_PROMOTION = 2

    INVITATION_SUBJECT = "Your invitation to sic"
    INVITATION_BODY = "Visit the following url to complete your registration:"
    INVITATION_FROM = settings.DEFAULT_FROM_EMAIL
    NOTIFICATION_FROM = settings.DEFAULT_FROM_EMAIL

    STORIES_PER_PAGE = 20

    FTS_DATABASE_NAME = "fts"
    FTS_DATABASE_FILENAME = "fts.db"
    FTS_COMMENTS_TABLE_NAME = "fts5_comments"
    FTS_STORIES_TABLE_NAME = "fts5_stories"

    MENTION_TOKENIZER_NAME = "mention_tokenizer"

    SEND_WEBMENTIONS = True

    def ready(self):
        import sic.notifications
        import sic.webmention

    @staticmethod
    @lru_cache(maxsize=None)
    def get_domain():
        from .models import Site

        return Site.objects.get_current().domain

    @staticmethod
    def make_msgid():
        domain = SicAppConfig.get_domain()
        return make_msgid(domain=domain)
