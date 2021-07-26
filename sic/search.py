from django.db import connections
from django.utils.safestring import mark_safe
from django.db.models.expressions import RawSQL
from django.db.models.signals import post_save, pre_delete
from django.db.backends.signals import connection_created
from django.dispatch import receiver
from django.conf import settings
from .apps import SicAppConfig as config
from .models import Comment, Story
import html


def run_once(f):
    def wrapper(*args, **kwargs):
        if not wrapper.has_run:
            try:
                ret = f(*args, **kwargs)
                wrapper.has_run = True
                return ret
            except Exception as exc:
                wrapper.previous_exception = exc
                raise exc from None

    wrapper.has_run = False
    wrapper.previous_exception = None
    return wrapper


@receiver(connection_created)
def fts5_setup(sender, connection, **kwargs):
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA database_list;")
        has_fts = False
        fts5_comments_table_exists = False
        fts5_stories_table_exists = False
        for row in cursor.fetchall():
            if row[1] == config.FTS_DATABASE_NAME:
                has_fts = True
                break
        if not has_fts:
            cursor.execute(
                f"ATTACH DATABASE :dbfname AS {config.FTS_DATABASE_NAME}",
                {
                    "dbfname": str(settings.BASE_DIR / config.FTS_DATABASE_FILENAME),
                },
            )
        cursor.execute(
            f"SELECT name FROM {config.FTS_DATABASE_NAME}.sqlite_master WHERE name = '{config.FTS_COMMENTS_TABLE_NAME}'"
        )
        try:
            fts5_comments_table_exists = len(cursor.fetchone()) != 0
        except:
            pass
        if not fts5_comments_table_exists:
            cursor.execute(
                f"CREATE VIRTUAL TABLE {config.FTS_DATABASE_NAME}.{config.FTS_COMMENTS_TABLE_NAME} USING fts5(id UNINDEXED, text);"
            )
        cursor.execute(
            f"SELECT name FROM {config.FTS_DATABASE_NAME}.sqlite_master WHERE name = '{config.FTS_STORIES_TABLE_NAME}'"
        )
        try:
            fts5_stories_table_exists = len(cursor.fetchone()) != 0
        except:
            pass
        if not fts5_stories_table_exists:
            cursor.execute(
                f"CREATE VIRTUAL TABLE {config.FTS_DATABASE_NAME}.{config.FTS_STORIES_TABLE_NAME} USING fts5(id UNINDEXED, title, description);"
            )


def index_comment(obj: Comment):
    text = html.escape(obj.text_to_plain_text())
    with connections["default"].cursor() as cursor:
        cursor.execute(
            f"INSERT OR REPLACE INTO {config.FTS_DATABASE_NAME}.{config.FTS_COMMENTS_TABLE_NAME}(id, text) VALUES (:id, :text)",
            {"id": obj.pk, "text": text},
        )


def index_story(obj: Story):
    with connections["default"].cursor() as cursor:
        cursor.execute(
            f"INSERT OR REPLACE INTO {config.FTS_DATABASE_NAME}.{config.FTS_STORIES_TABLE_NAME}(id, title, description) VALUES (:id, :title, :description)",
            {"id": obj.pk, "title": obj.title, "description": obj.description},
        )


def query_comments(query_string: str):
    escaped = html.escape(query_string)
    comments = (
        Comment.objects.all()
        .filter(
            id__in=RawSQL(
                f"select id from {config.FTS_DATABASE_NAME}.{config.FTS_COMMENTS_TABLE_NAME}('\"{escaped}\"')",
                (),
            ),
            deleted=False,
        )
        .order_by("-created")
    )
    with connections["default"].cursor() as cursor:
        cursor.execute(
            f"select id, snippet({config.FTS_COMMENTS_TABLE_NAME},-1,'<mark>','</mark>','\u200a[…]\u200a',36) as snippet from {config.FTS_DATABASE_NAME}.{config.FTS_COMMENTS_TABLE_NAME}('\"{escaped}\"')"
        )
        snippets = {i[0]: i[1] for i in cursor.fetchall()}
        for obj in comments:
            obj.snippet = mark_safe(snippets[obj.pk])
    return comments


@receiver(post_save, sender=Comment)
def comment_save_receiver(
    sender, instance, created, raw, using, update_fields, **kwargs
):
    if instance.deleted:
        comment_delete_receiver(sender, instance, using, **kwargs)
    else:
        index_comment(instance)


@receiver(pre_delete, sender=Comment)
def comment_delete_receiver(sender, instance, using, **kwargs):
    with connections["default"].cursor() as cursor:
        cursor.execute(
            f"DELETE FROM {config.FTS_DATABASE_NAME}.{config.FTS_COMMENTS_TABLE_NAME} WHERE id=:id",
            {"id": instance.pk},
        )
