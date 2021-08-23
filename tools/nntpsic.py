import re
import datetime
import sqlite3
import collections.abc

from nntp_server import *


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
        cur = self.server.conn.cursor()
        cur.execute("SELECT COUNT(id) AS count FROM sic_story")
        return cur.fetchone()["count"]

    @property
    def high(self):
        cur = self.server.conn.cursor()
        cur.execute("SELECT MAX(id) AS max FROM sic_story")
        return cur.fetchone()["max"]

    @property
    def low(self):
        cur = self.server.conn.cursor()
        cur.execute("SELECT MIN(id) AS min FROM sic_story")
        return cur.fetchone()["min"]

    @property
    def articles(self):
        return self.server


class SicNNTPServer(NNTPServer, collections.abc.Mapping):
    def __init__(self, *args, **kwargs):
        self.conn = sqlite3.connect("sic.db", detect_types=sqlite3.PARSE_DECLTYPES)
        self.conn.create_function("regexp", 2, sqlite_regexp, deterministic=True)
        self.conn.row_factory = sqlite3.Row
        self.all = SicAllStories(self)
        self._groups = {self.all.name: self.all}
        super().__init__(*args, **kwargs)

    @property
    def groups(self) -> typing.Dict[str, NNTPGroup]:
        return self._groups

    @property
    def articles(self):
        return self

    def __getitem__(self, key):
        if not isinstance(key, int):
            key = int(key)
        cur = self.conn.cursor()
        cur.execute(
            "SELECT u.username, s.* FROM sic_story AS s, sic_user AS u WHERE s.id = ? AND u.id = s.user_id",
            (key,),
        )
        story = cur.fetchone()
        return ArticleInfo(
            story["id"],
            story["title"],
            f"""{story["username"]}@sic.pm""",
            datetime.datetime.fromisoformat(story["created"]),
            f"""{story["id"]}@story.sic.pm""",
            "",
            len(story["url"]),
            1,
            {},
        )

    def __iter__(self):
        cur = self.conn.cursor()
        cur.execute("SELECT id FROM sic_story ORDER BY created DESC")
        return (self[row["id"]] for row in cur.fetchall())

    def __len__(self):
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(id) AS count FROM sic_story")
        return cur.fetchone["count"]

    def article(self, key: typing.Union[str, int]) -> Article:
        if not isinstance(key, int):
            key = int(key)
        cur = self.conn.cursor()
        cur.execute(
            "SELECT u.username, s.* FROM sic_story AS s, sic_user AS u WHERE s.id = ? AND u.id = s.user_id",
            (key,),
        )
        story = cur.fetchone()
        return Article(
            ArticleInfo(
                story["id"],
                story["title"],
                f"""{story["username"]}@sic.pm""",
                datetime.datetime.fromisoformat(story["created"]),
                f"""{story["id"]}@story.sic.pm""",
                "",
                len(story["url"]),
                1,
                {},
            ),
            story["url"],
        )


if __name__ == "__main__":
    HOST = "localhost"
    SicNNTPServer.allow_reuse_address = True

    # Create the server, binding to localhost on port 9999
    with SicNNTPServer((HOST, 9999), NNTPConnectionHandler) as server:
        server.allow_reuse_address = True
        # Activate the server; this will keep running until you
        # interrupt the program with Ctrl-C
        server.serve_forever()
