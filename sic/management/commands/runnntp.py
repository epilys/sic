import re
import sys
import heapq
import datetime
import sqlite3
import typing
import collections.abc
import importlib.util

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.module_loading import import_string

NNTP_SERVER_PATH = settings.BASE_DIR / "tools" / "nntpserver.py"
spec = importlib.util.spec_from_file_location("nntpserver", NNTP_SERVER_PATH)
nntpserver = importlib.util.module_from_spec(spec)
sys.modules["nntpserver"] = nntpserver
spec.loader.exec_module(nntpserver)

from nntpserver import *

from sic.models import Story, Comment
from sic.apps import SicAppConfig as config


def sqlite_regexp(re_pattern, re_string):
    return bool(re.search(re_pattern, str(re_string)))


class SicAllStories(NNTPGroup):
    def __init__(self, server):
        self._name = "all"
        self.server = server

    @property
    def name(self):
        return self._name

    @property
    def short_description(self):
        return self._name

    @property
    def number(self):
        return self.server.count

    @property
    def high(self):
        return self.server.high

    @property
    def low(self):
        return self.server.low

    @property
    def articles(self):
        return self.server


PK_MSG_ID_RE = re.compile(
    r"(?:story-(?P<story_pk>\d+))|(?:comment-(?P<comment_pk>\d+))"
)

MAKE_MSGID = lambda pk, msg_id, tag: msg_id if msg_id else f"<{tag}-{pk}@sic.pm>"
MSG_ID_RE = re.compile(r"^\s*<(?P<msg_id>[^>]+)>\s*")


def strip_msgid(msgid):
    m = MSG_ID_RE.search(msgid)
    if m:
        return m.group("msg_id")
    return m


class SicNNTPServer(NNTPServer, collections.abc.Mapping):
    overview_format: typing.List[str] = [
        "Subject:",
        "From:",
        "Date:",
        "Message-ID:",
        "References:",
        ":bytes",
        ":lines",
    ]

    def __init__(self, *args, **kwargs):
        self.all = SicAllStories(self)
        self._groups = {self.all.name: self.all}
        self.count = 0
        self.build_index()
        super().__init__(*args, **kwargs)

    @property
    def groups(self) -> typing.Dict[str, NNTPGroup]:
        return self._groups

    @property
    def articles(self):
        return self

    def get_story(self, message_id, story_pk=None):
        # print("get_story", message_id, story_pk)
        if story_pk:
            return Story.objects.filter(pk=story_pk).first()
        else:
            return Story.objects.filter(message_id=message_id).first()

    def get_comment(self, message_id, comment_pk=None):
        # print("get_comment", message_id, comment_pk)
        if comment_pk:
            return Comment.objects.filter(pk=comment_pk).first()
        else:
            return Comment.objects.filter(message_id=message_id).first()

    def __getitem__(self, key: typing.Union[str, int]) -> ArticleInfo:
        # print("key=", key, type(key))
        if isinstance(key, str):
            try:
                key = int(key.strip())
            except:
                pass
        if isinstance(key, int):
            key = self.index[key][0]
        key = key.strip()
        pk_search = PK_MSG_ID_RE.search(key)
        # print(key, pk_search, type(pk_search))
        try:
            story = self.get_story(
                key,
                story_pk=(
                    pk_search.group("story_pk")
                    if pk_search and pk_search.group("story_pk")
                    else None
                ),
            )
            # print("get_story returned ", story)
            return ArticleInfo(
                self.reverse_index[key],
                story.title,
                f"""{story.user.username}@sic.pm""",
                story.created,
                key,
                "",
                len(story.url) if story.url else len(story.description),
                1,
                {},
            )
        except Exception as exc:
            pass
            # print("Exception:", exc)
        try:
            comment = self.get_comment(
                key,
                comment_pk=(
                    pk_search.group("comment_pk")
                    if pk_search and pk_search.group("comment_pk")
                    else None
                ),
            )
            # print("get_comment returned ", comment)
            if comment.parent_id:
                parent = self.get_comment("", comment_pk=comment.parent_id)
                references = MAKE_MSGID(parent.id, parent.message_id, "comment")
            else:
                parent = self.get_story("", story_pk=comment.story_id)
                references = MAKE_MSGID(parent.id, parent.message_id, "story")
            return ArticleInfo(
                self.reverse_index[key],
                f"Re: {comment.story.title}",
                f"""{comment.user.username}@sic.pm""",
                comment.created,
                key,
                references,
                len(comment.text),
                1,
                {},
            )
        except TypeError as exc:
            raise exc

    def __iter__(self):
        return (self[k] for k in self.index)

    def __len__(self):
        return self.count

    def article(self, key: typing.Union[str, int]) -> Article:
        # print("def article key = ", key, type(key))
        if isinstance(key, str):
            try:
                key = int(key.strip())
            except:
                pass
        if isinstance(key, int):
            key = self.index[key][0]
        key = key.strip()
        pk_search = PK_MSG_ID_RE.search(key)
        try:
            story = self.get_story(
                key,
                story_pk=pk_search.group("story_pk")
                if pk_search and pk_search.group("story_pk")
                else None,
            )
            # print("get_story returned ", story)
            return Article(
                ArticleInfo(
                    self.reverse_index[key],
                    story.title,
                    f"""{story.user.username}@sic.pm""",
                    story.created,
                    key,
                    "",
                    len(story.url) if story.url else len(story.description),
                    1,
                    {"URL": f"{config.get_domain()}{story.get_absolute_url()}"},
                ),
                story.url if story.url else story.description,
            )
        except Exception as exc:
            # print("Exception,", exc)
            pass
        try:
            comment = self.get_comment(
                key,
                comment_pk=pk_search.group("comment_pk")
                if pk_search and pk_search.group("comment_pk")
                else None,
            )
            # print("get_comment returned ", comment)
            if comment.parent_id:
                parent = self.get_comment("", comment_pk=comment.parent_id)
                references = MAKE_MSGID(parent.id, parent.message_id, "comment")
            else:
                parent = self.get_story("", story_pk=comment.story_id)
                references = MAKE_MSGID(parent.id, parent.message_id, "story")
            return Article(
                ArticleInfo(
                    self.reverse_index[key],
                    f"Re: {comment.story.title}",
                    f"""{comment.user.username}@sic.pm""",
                    comment.created,
                    key,
                    references,
                    len(comment.text),
                    1,
                    {"URL": f"{config.get_domain()}{comment.get_absolute_url()}"},
                ),
                comment.text,
            )
        except TypeError as exc:
            raise exc

    def build_index(self):
        self.index = {}
        self.count = 0
        self.high = 0
        self.low = 0
        stories = (
            (MAKE_MSGID(story.id, story.message_id, "story"), story.created)
            for story in Story.objects.order_by("created")
        )
        comments = (
            (MAKE_MSGID(comment.id, comment.message_id, "comment"), comment.created)
            for comment in Comment.objects.order_by("created")
        )
        self.index = dict(enumerate(heapq.merge(stories, comments, key=lambda e: e[1])))
        self.reverse_index = {self.index[k][0]: k for k in self.index}
        print("index", self.index)
        print("\n\nrevindex", self.reverse_index)
        self.high = len(self.index)
        self.count = len(self.index)
        return


class Command(BaseCommand):
    help = "Run NNTP server"

    def handle(self, *args, **kwargs):
        HOST = "localhost"
        SicNNTPServer.allow_reuse_address = True

        # Create the server, binding to localhost on port 9999
        with SicNNTPServer((HOST, 9999), NNTPConnectionHandler) as server:
            server.allow_reuse_address = True
            # Activate the server; this will keep running until you
            # interrupt the program with Ctrl-C
            server.serve_forever()
