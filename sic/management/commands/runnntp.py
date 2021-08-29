import re
import sys
import heapq
import datetime
import sqlite3
import typing
import threading
import collections.abc
import importlib.util

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.module_loading import import_string

NNTP_SERVER_PATH = settings.BASE_DIR / "tools" / "nntpserver.py"
spec = importlib.util.spec_from_file_location("nntpserver", NNTP_SERVER_PATH)
if spec is None or spec.loader is None:
    raise ImportError("Could not find nntpserver.py under tools/ dir.")
nntpserver = importlib.util.module_from_spec(spec)
sys.modules["nntpserver"] = nntpserver
spec.loader.exec_module(nntpserver)  # type: ignore

from nntpserver import (
    NNTPServer,
    NNTPGroup,
    NNTPConnectionHandler,
    Article,
    ArticleInfo,
)
from sic.models import Story, Comment
from django.apps import apps

config = apps.get_app_config("sic")


class SicAllStories(NNTPGroup):
    def __init__(self, server: NNTPServer) -> None:
        self._name: str = "sic.all"
        self.server: NNTPServer = server

    @property
    def name(self) -> str:
        return self._name

    @property
    def short_description(self) -> str:
        return self._name

    @property
    def number(self) -> int:
        return self.server.count

    @property
    def high(self) -> int:
        return self.server.high

    @property
    def low(self) -> int:
        return self.server.low

    @property
    def articles(self) -> typing.Dict[int, ArticleInfo]:
        return self.server


PK_MSG_ID_RE = re.compile(
    r"(?:story-(?P<story_pk>\d+))|(?:comment-(?P<comment_pk>\d+))"
)

MAKE_MSGID: typing.Callable[[int, str, str], str] = (
    lambda pk, msg_id, tag: msg_id if msg_id else f"<{tag}-{pk}@sic.pm>"
)
MSG_ID_RE = re.compile(r"^\s*<(?P<msg_id>[^>]+)>\s*")


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

    def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        self.all: SicAllStories = SicAllStories(self)
        self._groups: typing.Dict[str, SicAllStories] = {self.all.name: self.all}
        self.count: int = 0
        self.high: int = 0
        self.low: int = 0
        self.build_index()
        super().__init__(*args, **kwargs)

    @property
    def groups(self) -> typing.Dict[str, NNTPGroup]:
        return self._groups

    @property
    def articles(self) -> typing.Dict[int, ArticleInfo]:
        return self

    def get_story(
        self, message_id: str, story_pk: typing.Optional[int] = None
    ) -> Story:
        # print("get_story", message_id, story_pk)
        if story_pk:
            return Story.objects.filter(pk=story_pk).first()
        else:
            return Story.objects.filter(message_id=message_id).first()

    def get_comment(
        self, message_id: str, comment_pk: typing.Optional[int] = None
    ) -> Comment:
        # print("get_comment", message_id, comment_pk)
        if comment_pk:
            return Comment.objects.filter(pk=comment_pk).first()
        else:
            return Comment.objects.filter(message_id=message_id).first()

    def __getitem__(self, key: typing.Union[str, int]) -> ArticleInfo:
        # print("key=", key, type(key))
        if isinstance(key, ArticleInfo):  # FIXME: is this a bug?
            return key
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
                    int(pk_search.group("story_pk"))
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
                    int(pk_search.group("comment_pk"))
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

    def __iter__(self) -> typing.Iterator[typing.Any]:
        return (self[k] for k in self.index)

    def __len__(self) -> int:
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
                story_pk=int(pk_search.group("story_pk"))
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
                comment_pk=int(pk_search.group("comment_pk"))
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

    def build_index(self) -> None:
        self.index: typing.Dict[int, typing.Tuple[str, datetime.datetime]] = {}
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
        self.high = len(self.index)
        self.count = len(self.index)
        return


class Command(BaseCommand):
    help = "Run NNTP server"

    def add_arguments(self, parser: typing.Any) -> None:
        parser.add_argument("--port", type=int, default=9999)
        parser.add_argument("--host", type=str, default="localhost")
        parser.add_argument("--use_ssl", action="store_true", default=False)
        parser.add_argument("--certfile", type=str, default=None)
        parser.add_argument("--keyfile", type=str, default=None)

    def handle(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        HOST = kwargs["host"]
        PORT = kwargs["port"]
        USE_SSL = kwargs["use_ssl"]
        server_kwargs = {}
        if USE_SSL:
            server_kwargs["use_ssl"] = True
            server_kwargs["certfile"] = kwargs["certfile"]
            server_kwargs["keyfile"] = kwargs["keyfile"]

        SicNNTPServer.allow_reuse_address = True

        # Create the server, binding to localhost on port 9999
        with SicNNTPServer(
            (HOST, PORT), NNTPConnectionHandler, **server_kwargs
        ) as server:
            print(f"Listening on {HOST}:{PORT}")
            server.allow_reuse_address = True
            # Activate the server; this will keep running until you
            # interrupt the program with Ctrl-C
            server_thread = threading.Thread(target=server.serve_forever)
            server_thread.daemon = True
            server_thread.start()
            try:
                server_thread.join()
            except KeyboardInterrupt:
                pass
            finally:
                server.shutdown()
