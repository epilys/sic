import re
import sys
import email
import heapq
import secrets
import datetime
import sqlite3
import typing
import threading
import collections.abc
import importlib.util
from email.policy import default as email_policy

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.module_loading import import_string
from django.contrib.auth import authenticate

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
    NNTPAuthSetting,
    NNTPAuthenticationError,
    NNTPPostSetting,
    NNTPPostError,
    NNTPArticleNotFound,
    NNTPServerError,
    Article,
    ArticleInfo,
)
from sic.models import Story, Comment, User
from sic.mail import post_receive
from django.apps import apps

config = apps.get_app_config("sic")


class SicAllStories(NNTPGroup):
    def __init__(self, server: NNTPServer) -> None:
        self._name: str = f"{config.verbose_name.replace(' ','_')}.all"
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
    def articles(self) -> typing.Dict[typing.Union[int, str], ArticleInfo]:
        return self.server

    @property
    def created(self) -> datetime.datetime:
        return datetime.datetime.fromtimestamp(0, datetime.timezone.utc)

    @property
    def posting_permitted(self) -> bool:
        return True


PK_MSG_ID_RE = re.compile(
    r"(?:story-(?P<story_pk>\d+))|(?:comment-(?P<comment_pk>\d+))"
)

MAKE_MSGID: typing.Callable[[int, str, str], str] = (
    lambda pk, msg_id, tag: msg_id if msg_id else f"<{tag}-{pk}@{config.get_domain()}>"
)
MSG_ID_RE = re.compile(r"^\s*<(?P<msg_id>[^>]+)>\s*")


class SicNNTPServer(NNTPServer, collections.abc.Mapping):
    overview_format: typing.List[str] = [
        "Subject:",
        "From:",
        "Date:",
        "Message-ID:",
        "References:",
        "Bytes:",
        "Lines:",
    ]

    def __init__(self, *args: typing.Any, **kwargs: typing.Any) -> None:
        self.all: SicAllStories = SicAllStories(self)
        self._groups: typing.Dict[str, SicAllStories] = {self.all.name: self.all}
        self.count: int = 0
        self.high: int = 0
        self.low: int = 0

        self.last_modified = datetime.datetime.fromtimestamp(0, datetime.timezone.utc)
        self.build_index()
        self.authed_sessions: typing.Dict[bytes, int] = {}
        super().__init__(*args, **kwargs)

    def refresh(self) -> None:
        """Hook for refreshing internal state before processing article/group commands"""
        self.last_modified
        try:
            if (
                self.last_modified
                < Story.objects.filter(last_modified__isnull=False)
                .latest("last_modified")
                .last_modified
            ):
                self.build_index()
                return
        except Story.DoesNotExist:
            pass
        try:
            if (
                self.last_modified
                < Comment.objects.filter(last_modified__isnull=False)
                .latest("last_modified")
                .last_modified
            ):
                self.build_index()
                return
        except Comment.DoesNotExist:
            pass

    @property
    def groups(self) -> typing.Dict[str, NNTPGroup]:
        return self._groups

    @property
    def articles(self) -> typing.Dict[typing.Union[int, str], ArticleInfo]:
        return self

    def get_story(
        self, message_id: str, story_pk: typing.Optional[int] = None
    ) -> Story:
        # print("get_story", message_id, story_pk)
        if story_pk:
            return Story.objects.filter(pk=story_pk, active=True).first()
        else:
            return Story.objects.filter(message_id=message_id, active=True).first()

    def get_comment(
        self, message_id: str, comment_pk: typing.Optional[int] = None
    ) -> Comment:
        # print("get_comment", message_id, comment_pk)
        if comment_pk:
            return Comment.objects.filter(pk=comment_pk).first()
        else:
            return Comment.objects.filter(message_id=message_id).first()

    def __getitem__(self, key: typing.Union[str, int]) -> ArticleInfo:
        return self.article(key).info

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
            if key < self.low or key > self.high:
                raise NNTPArticleNotFound(str(key))
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
            if not story:
                raise NNTPArticleNotFound(key)
            return Article(
                ArticleInfo(
                    self.reverse_index[key],
                    story.title,
                    f"""{story.user.username}@{config.get_domain()}""",
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
            if not comment or not comment.story.active:
                raise NNTPArticleNotFound(key)
            if comment.parent_id:
                parent = self.get_comment("", comment_pk=comment.parent_id)
                if parent:
                    references = MAKE_MSGID(parent.id, parent.message_id, "comment")
            else:
                parent = self.get_story("", story_pk=comment.story_id)
                if not parent:
                    raise NNTPArticleNotFound(key)
                references = MAKE_MSGID(parent.id, parent.message_id, "story")
            return Article(
                ArticleInfo(
                    self.reverse_index[key],
                    f"Re: {comment.story.title}",
                    f"""{comment.user.username}@{config.get_domain()}""",
                    comment.created,
                    key,
                    references,
                    len(comment.text),
                    1,
                    {"URL": f"{config.get_domain()}{comment.get_absolute_url()}"},
                ),
                comment.text,
            )
        except NNTPArticleNotFound as exc:
            pass
        except Exception as exc:
            print("Exception: ", exc)
            raise NNTPServerError(str(exc)) from exc
        raise NNTPArticleNotFound(key)

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
        self.index = dict(
            map(
                lambda e: (e[0] + 1, e[1]),
                enumerate(heapq.merge(stories, comments, key=lambda e: (e[1], e[0]))),
            )
        )
        self.reverse_index = {self.index[k][0]: k for k in self.index}
        self.high = max(self.index) if self.index else 0
        self.count = self.high
        self.low = 1 if self.high != 0 else 0

        try:
            self.last_modified = max(
                self.last_modified,
                Story.objects.filter(last_modified__isnull=False)
                .latest("last_modified")
                .last_modified,
            )
        except Story.DoesNotExist:
            pass
        try:
            self.last_modified = max(
                self.last_modified,
                Comment.objects.filter(last_modified__isnull=False)
                .latest("last_modified")
                .last_modified,
            )
        except Comment.DoesNotExist:
            pass
        return

    def auth_user(self, username: str, password: str) -> bytes:
        user: User = authenticate(
            username=username, password=password, username_as_alternative=True
        )
        if user is None:
            raise NNTPAuthenticationError("Authentication failed")
        auth_token: typing.Optional[bytes] = next(
            (token for token, pk in self.authed_sessions.items() if pk == user.pk), None
        )
        if auth_token:
            return auth_token

        auth_token = secrets.token_bytes()
        retries = 0
        while auth_token in self.authed_sessions:
            auth_token = secrets.token_bytes()  # prevent duplicates
            retries += 1
            if retries > 3:
                raise NNTPAuthenticationError("Authentication failed: Internal Error")
        self.authed_sessions[auth_token] = user.pk
        return auth_token

    def post(self, auth_token: typing.Optional[bytes], lines: str) -> None:
        if not auth_token or auth_token not in self.authed_sessions:
            raise NNTPPostError("Authentication required")
        if not lines.strip():
            raise NNTPPostError("Received empty article.")
        print("got new post: ", lines)
        user_pk: int = self.authed_sessions[auth_token]
        try:
            user = User.objects.get(pk=user_pk)
        except User.DoesNotExist:
            raise NNTPPostError("User not found.")
        try:
            msg = email.message_from_string(lines, policy=email_policy)
            if not msg["message-id"]:
                lines = (
                    f"Message-ID: <nntp-{secrets.token_hex(16)}@{config.get_domain()}>\r\n"
                    + lines
                )
            ret_str = post_receive(lines, user=user)
            print(f"post_receive() for user {user} returned: ", ret_str)
        except Exception as exc:
            raise NNTPPostError(str(exc)) from exc

    @property
    def subscriptions(self) -> typing.Optional[typing.List[str]]:
        return [self.all.name]

    @property
    def debugging(self) -> bool:
        return True


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
        server_kwargs["auth"] = NNTPAuthSetting.SECUREONLY
        server_kwargs["can_post"] = NNTPPostSetting.AUTHREQUIRED

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
