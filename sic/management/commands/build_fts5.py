from django.core.management.base import BaseCommand
from django.db import connections
from sic.models import Comment
from sic.apps import SicAppConfig as config
from sic.search import fts5_setup, index_comment


class Command(BaseCommand):
    help = "(Re)Build fts5 index"

    def handle(self, *args, **kwargs):
        with connections["default"].cursor() as cursor:
            cursor.execute(
                f"DELETE FROM {config.FTS_DATABASE_NAME}.{config.FTS_COMMENTS_TABLE_NAME}"
            )
        comments = Comment.objects.filter(deleted=False)
        for c in comments:
            index_comment(c)
