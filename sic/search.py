from django.utils.safestring import mark_safe
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.conf import settings
from .apps import SicAppConfig as config
from .models import Comment, Story
import html
import re
import os
import sqlite3
import threading


def escape_fts(query):
    query = query.replace("'", "")
    query = query.replace("&", "")
    query = query.replace("!", "")
    query = query.replace("#", "")
    query = query.replace("$", "")
    query = query.replace("%", "")
    query = query.replace('"', "")
    return query


def run_once(f):
    def wrapper(*args, **kwargs):
        if not hasattr(wrapper.has_run, "value") or not wrapper.has_run.value:
            try:
                wrapper.has_run.value = f(*args, **kwargs)
            except Exception as exc:
                wrapper.previous_exception = exc
                raise exc from None
        return wrapper.has_run.value

    wrapper.has_run = threading.local()
    wrapper.has_run.__setattr__("value", False)
    wrapper.previous_exception = None
    return wrapper


@run_once
def fts5_setup():
    dbfname = str(settings.BASE_DIR / config.FTS_DATABASE_FILENAME)
    exists = os.path.exists(dbfname)
    connection = sqlite3.connect(dbfname)
    with connection:
        connection.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {config.FTS_COMMENTS_TABLE_NAME} USING fts5(id UNINDEXED, text);"
        )
        connection.execute(
            f"CREATE TABLE IF NOT EXISTS {config.FTS_STORIES_TABLE_NAME}_content (id INTEGER PRIMARY KEY, title TEXT, description TEXT, url TEXT, remote_content TEXT);"
        )
        connection.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {config.FTS_STORIES_TABLE_NAME} USING fts5(id UNINDEXED, title, description, url, remote_content, content={config.FTS_STORIES_TABLE_NAME}_content, content_rowid=id);"
        )
    return connection


#        cursor.execute(
#            f"""CREATE TEMP TRIGGER IF NOT EXISTS on_insert_story_ins AFTER INSERT ON main.sic_storyremotecontent FOR EACH ROW
# BEGIN
#    INSERT OR IGNORE INTO {config.FTS_STORIES_TABLE_NAME}_content (id) VALUES (NEW.story_id);
#    UPDATE {config.FTS_STORIES_TABLE_NAME}_content SET remote_content = NEW.content WHERE id = NEW.story_id;
#    UPDATE {config.FTS_STORIES_TABLE_NAME} SET remote_content = NEW.content WHERE id = NEW.story_id;
# END;"""
#        )
#        cursor.execute(
#            f"""CREATE TEMP TRIGGER IF NOT EXISTS on_insert_story_upd AFTER UPDATE of content ON main.sic_storyremotecontent FOR EACH ROW
# BEGIN
#    INSERT OR IGNORE INTO {config.FTS_STORIES_TABLE_NAME}_content (id) VALUES (NEW.story_id);
#    UPDATE {config.FTS_STORIES_TABLE_NAME}_content SET remote_content = NEW.content WHERE id = NEW.story_id;
#    UPDATE {config.FTS_STORIES_TABLE_NAME} SET remote_content = NEW.content WHERE id = NEW.story_id;
# END;"""
#        )
#        cursor.execute(
#            f"""CREATE TEMP TRIGGER IF NOT EXISTS on_insert_story_del AFTER DELETE ON main.sic_storyremotecontent FOR EACH ROW
# BEGIN
#    INSERT OR IGNORE INTO {config.FTS_STORIES_TABLE_NAME}_content (id) VALUES (NEW.story_id);
#    UPDATE {config.FTS_STORIES_TABLE_NAME}_content SET remote_content = NULL WHERE id = NEW.story_id;
#    UPDATE {config.FTS_STORIES_TABLE_NAME} SET remote_content = NULL WHERE id = NEW.story_id;
# END;"""
#        )
#        cursor.execute(
#            f"""CREATE TRIGGER IF NOT EXISTS {config.FTS_STORIES_TABLE_NAME}_content_ai AFTER INSERT ON {config.FTS_STORIES_TABLE_NAME}_content
# BEGIN
#    INSERT INTO {config.FTS_STORIES_TABLE_NAME}(rowid, title, description, url, remote_content)
#        VALUES (NEW.id, NEW.title, NEW.description, NEW.url, NULL);
# END;"""
#        )
#        cursor.execute(
#            f"""CREATE TRIGGER IF NOT EXISTS {config.FTS_STORIES_TABLE_NAME}_content_ad AFTER DELETE ON {config.FTS_STORIES_TABLE_NAME}_content
# BEGIN
#    DELETE FROM {config.FTS_STORIES_TABLE_NAME} WHERE id = OLD.id;
# END;"""
#        )
#
#        cursor.execute(
#            f"""CREATE TRIGGER IF NOT EXISTS {config.FTS_STORIES_TABLE_NAME}_content_au AFTER UPDATE ON {config.FTS_STORIES_TABLE_NAME}_content
# BEGIN
#    DELETE FROM {config.FTS_STORIES_TABLE_NAME} WHERE id = OLD.id;
#    INSERT INTO {config.FTS_STORIES_TABLE_NAME}(rowid, title, description, url, remote_content)
#        VALUES (NEW.id, NEW.title, NEW.description, NEW.url, NULL);
# END;"""
#        )


def index_comment(obj: Comment):
    connection = fts5_setup()
    text = html.escape(obj.text_to_plain_text)
    with connection:
        connection.execute(
            f"INSERT OR REPLACE INTO {config.FTS_COMMENTS_TABLE_NAME}(rowid, text) VALUES (:id, :text)",
            {"id": obj.pk, "text": text},
        )


def index_story(obj: Story):
    connection = fts5_setup()
    try:
        remote_content = obj.remote_content.content
    except:
        remote_content = None
    with connection:
        connection.execute(
            f"INSERT OR REPLACE INTO {config.FTS_STORIES_TABLE_NAME}_content(id, title, description, remote_content) VALUES (:id, :title, :description, :remote_content)",
            {
                "id": obj.pk,
                "title": obj.title,
                "description": obj.description_to_plain_text.strip(),
                "remote_content": remote_content,
            },
        )
        connection.execute(
            f"INSERT OR REPLACE INTO {config.FTS_STORIES_TABLE_NAME}(rowid, title, description, url, remote_content) VALUES (:id, :title, :description, :url, :remote_content)",
            {
                "id": obj.pk,
                "title": obj.title,
                "description": obj.description_to_plain_text.strip(),
                "url": obj.url,
                "remote_content": remote_content,
            },
        )


def query_comments(query_string: str):
    connection = fts5_setup()
    with connection:
        comments = (
            Comment.objects.all()
            .filter(
                id__in=[
                    r[0]
                    for r in connection.execute(
                        f"select id from {config.FTS_COMMENTS_TABLE_NAME}('\"{escape_fts(query_string)}\"')",
                    )
                ],
                deleted=False,
            )
            .order_by("-created")
        )

        snippets = {
            i[0]: i[1]
            for i in connection.execute(
                f"select id, snippet({config.FTS_COMMENTS_TABLE_NAME},-1,'<mark>','</mark>','\u200a[…]\u200a',36) as snippet from {config.FTS_COMMENTS_TABLE_NAME}('\"{escape_fts(query_string)}\"')"
            )
        }
        for obj in comments:
            obj.snippet = mark_safe(snippets[obj.pk])
    return comments


def query_stories(query_string: str):
    connection = fts5_setup()
    with connection:
        stories = (
            Story.objects.all()
            .filter(
                id__in=[
                    r[0]
                    for r in connection.execute(
                        f"select id from {config.FTS_STORIES_TABLE_NAME}('\"{escape_fts(query_string)}\"')",
                    )
                ],
                active=True,
            )
            .order_by("-created")
        )

        snippets = {
            i[0]: i[1]
            for i in connection.execute(
                f"select id, snippet({config.FTS_STORIES_TABLE_NAME},-1,'<mark>','</mark>','\u200a[…]\u200a',36) as snippet from {config.FTS_STORIES_TABLE_NAME}('\"{escape_fts(query_string)}\"')"
            )
        }
        for obj in stories:
            obj.snippet = mark_safe(snippets[obj.pk])
    return stories


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
    connection = fts5_setup()
    with connection:
        connection.execute(
            f"DELETE FROM {config.FTS_COMMENTS_TABLE_NAME} WHERE id=:id",
            {"id": instance.pk},
        )
