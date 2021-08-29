from django.core.management.base import BaseCommand
from django.db import connections, transaction
from django.apps import apps

config = apps.get_app_config("sic")
from sic.models import Comment, Story
from sic.search import fts5_setup, index_comment, index_story


class Command(BaseCommand):
    help = "(Re)Build fts5 index"

    @transaction.atomic
    def handle(self, *args, **kwargs):
        # with connections["default"].cursor() as cursor:
        #    cursor.execute(
        #        f"DELETE FROM {config.FTS_DATABASE_NAME}.{config.FTS_COMMENTS_TABLE_NAME}"
        #    )
        comments = Comment.objects.filter(deleted=False)
        for c in comments:
            index_comment(c)
        stories = Story.objects.filter(active=True, merged_into=None)
        for s in stories:
            index_story(s)
