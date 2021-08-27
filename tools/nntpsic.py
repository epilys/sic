import re
import heapq
import datetime
import sqlite3
import collections.abc

from nntpserver import *


def sqlite_regexp(re_pattern, re_string):
    return bool(re.search(re_pattern, str(re_string)))


class SicAggregation(NNTPGroup):
    def __init__(self, conn, name, id):
        self._name = name
        self.id = id
        self.conn = conn

    @property
    def name(self):
        return self._name

    @property
    def short_description(self):
        return self._name

    @property
    def number(self):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT COUNT(DISTINCT s.id) AS count FROM taggregation_stories AS s JOIN sic_taggregation as agg ON s.taggregation_id = agg.id WHERE agg.'id' = ?",
            (self.id,),
        )
        return cur.fetchone()["count"]

    @property
    def high(self):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT MAX(s.id) AS max FROM taggregation_stories AS s JOIN sic_taggregation as agg ON s.taggregation_id = agg.id WHERE agg.'id' = ?",
            (self.id,),
        )
        return cur.fetchone()["max"]

    @property
    def low(self):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT MIN(s.id) AS min FROM taggregation_stories AS s JOIN sic_taggregation as agg ON s.taggregation_id = agg.id WHERE agg.'id' = ?",
            (self.id,),
        )
        return cur.fetchone()["min"]

    @property
    def articles(self):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM sic_story WHERE id IN (SELECT DISTINCT s.id FROM taggregation_stories AS s JOIN sic_taggregation as agg ON s.taggregation_id = agg.id WHERE agg.'id' = ?) ORDER BY created DESC",
            (self.id,),
        )
        return self.server


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
    def __init__(self, *args, **kwargs):
        self.conn = sqlite3.connect("sic.db", detect_types=sqlite3.PARSE_DECLTYPES)
        self.conn.create_function("regexp", 2, sqlite_regexp, deterministic=True)
        self.conn.row_factory = sqlite3.Row
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
        cur = self.conn.cursor()
        print("get_story", message_id, story_pk)
        if story_pk:
            cur.execute(
                "SELECT u.username, s.* FROM sic_story AS s, sic_user AS u WHERE s.id = ? AND u.id = s.user_id",
                (story_pk,),
            )
        else:
            cur.execute(
                "SELECT u.username, s.* FROM sic_story AS s, sic_user AS u WHERE s.message_id = ? AND u.id = s.user_id",
                (strip_msgid(message_id),),
            )
        return cur.fetchone()

    def get_comment(self, message_id, comment_pk=None):
        cur = self.conn.cursor()
        print("get_comment", message_id, comment_pk)
        if comment_pk:
            cur.execute(
                "SELECT u.username, c.*, s.title as title FROM sic_comment AS c, sic_user AS u, sic_story as s WHERE c.id = ? AND u.id = c.user_id AND c.story_id = s.id",
                (comment_pk,),
            )
        else:
            cur.execute(
                "SELECT u.username, c.*, s.title as title FROM sic_comment AS c, sic_user AS u, sic_story as s WHERE c.message_id = ? AND u.id = c.user_id AND c.story_id = s.id",
                (strip_msgid(message_id),),
            )
        return cur.fetchone()

    def __getitem__(self, key: typing.Union[str, int]) -> ArticleInfo:
        if isinstance(key, int):
            key = self.index[key][0]
        key = key.strip()
        pk_search = PK_MSG_ID_RE.search(key)
        print(key, pk_search, type(pk_search))
        try:
            story = self.get_story(
                key,
                story_pk=(
                    pk_search.group("story_pk")
                    if pk_search and pk_search.group("story_pk")
                    else None
                ),
            )
            print("get_story returned ", story)
            return ArticleInfo(
                self.reverse_index[key],
                story["title"],
                f"""{story["username"]}@sic.pm""",
                datetime.datetime.fromisoformat(story["created"]),
                key,
                "",
                len(story["url"]) if story["url"] else len(story["description"]),
                1,
                {},
            )
        except Exception as exc:
            print("Exception:", exc)
        try:
            comment = self.get_comment(
                key,
                comment_pk=(
                    pk_search.group("comment_pk")
                    if pk_search and pk_search.group("comment_pk")
                    else None
                ),
            )
            print("get_comment returned ", dict(comment))
            if comment["parent_id"]:
                parent = self.get_comment("", comment_pk=comment["parent_id"])
                references = MAKE_MSGID(parent["id"], parent["message_id"], "comment")
            else:
                parent = self.get_story("", story_pk=comment["story_id"])
                references = MAKE_MSGID(parent["id"], parent["message_id"], "story")
            return ArticleInfo(
                self.reverse_index[key],
                f"Re: {comment['title']}",
                f"""{comment["username"]}@sic.pm""",
                datetime.datetime.fromisoformat(comment["created"]),
                key,
                references,
                len(comment["text"]),
                1,
                {},
            )
        except TypeError as exc:
            raise KeyError from exc

    def __iter__(self):
        return (self[k] for k in self.index)

    def __len__(self):
        return self.count

    def article(self, key: typing.Union[str, int]) -> Article:
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
            print("get_story returned ", story)
            return Article(
                ArticleInfo(
                    self.reverse_index[key],
                    story["title"],
                    f"""{story["username"]}@sic.pm""",
                    datetime.datetime.fromisoformat(story["created"]),
                    key,
                    "",
                    len(story["url"]) if story["url"] else len(story["description"]),
                    1,
                    {},
                ),
                story["url"] if story["url"] else story["description"],
            )
        except Exception as exc:
            print("Exception,", exc)
        try:
            comment = self.get_comment(
                key,
                comment_pk=pk_search.group("comment_pk")
                if pk_search and pk_search.group("comment_pk")
                else None,
            )
            print("get_comment returned ", dict(comment))
            if comment["parent_id"]:
                parent = self.get_comment("", comment_pk=comment["parent_id"])
                references = MAKE_MSGID(parent["id"], parent["message_id"], "comment")
            else:
                parent = self.get_story("", story_pk=comment["story_id"])
                references = MAKE_MSGID(parent["id"], parent["message_id"], "story")
            return Article(
                ArticleInfo(
                    self.reverse_index[key],
                    f"Re: {comment['title']}",
                    f"""{comment["username"]}@sic.pm""",
                    datetime.datetime.fromisoformat(comment["created"]),
                    key,
                    references,
                    len(comment["text"]),
                    1,
                    {},
                ),
                comment["text"],
            )
        except TypeError as exc:
            raise KeyError from exc

    def build_index(self):
        self.index = {}
        self.count = 0
        self.high = 0
        self.low = 0
        cur = self.conn.cursor()
        cur.execute(
            "SELECT id, message_id, created FROM sic_story ORDER BY created ASC"
        )
        stories = (
            (MAKE_MSGID(row["id"], row["message_id"], "story"), row["created"])
            for row in cur.fetchall()
        )
        cur.execute(
            "SELECT id, message_id, created FROM sic_comment ORDER BY created ASC"
        )
        comments = (
            (MAKE_MSGID(row["id"], row["message_id"], "comment"), row["created"])
            for row in cur.fetchall()
        )
        self.index = dict(enumerate(heapq.merge(stories, comments, key=lambda e: e[1])))
        self.reverse_index = {self.index[k][0]: k for k in self.index}
        self.high = len(self.index)
        self.count = len(self.index)
        return


if __name__ == "__main__":
    HOST = "localhost"
    SicNNTPServer.allow_reuse_address = True

    # Create the server, binding to localhost on port 9999
    with SicNNTPServer((HOST, 9999), NNTPConnectionHandler) as server:
        server.allow_reuse_address = True
        # Activate the server; this will keep running until you
        # interrupt the program with Ctrl-C
        server.serve_forever()
