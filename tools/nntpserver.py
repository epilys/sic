import abc
import socketserver
import collections
import typing
import datetime

from email.header import decode_header as _email_decode_header
import email.utils

# Standard port used by NNTP servers
NNTP_PORT = 119
NNTP_SSL_PORT = 563
_MAXLINE = 2048

_CRLF = b"\r\n"

# Default decoded value for LIST OVERVIEW.FMT if not supported
_DEFAULT_OVERVIEW_FMT = [
    "Subject:",
    "From:",
    "Date:",
    "Message-ID:",
    "References:",
    ":bytes",
    ":lines",
]


def format_datetime(dt, legacy=False):
    """Format a date or datetime object as a pair of (date, time) strings
    in the format required by the NEWNEWS and NEWGROUPS commands.  If a
    date object is passed, the time is assumed to be midnight (00h00).

    The returned representation depends on the legacy flag:
    * if legacy is False (the default):
      date has the YYYYMMDD format and time the HHMMSS format
    * if legacy is True:
      date has the YYMMDD format and time the HHMMSS format.
    RFC 3977 compliant servers should understand both formats; therefore,
    legacy is only needed when talking to old servers.
    """
    if not isinstance(dt, datetime.datetime):
        time_str = "000000"
    else:
        time_str = "{0.hour:02d}{0.minute:02d}{0.second:02d}".format(dt)
    y = dt.year
    if legacy:
        y = y % 100
        date_str = "{0:02d}{1.month:02d}{1.day:02d}".format(y, dt)
    else:
        date_str = "{0:04d}{1.month:02d}{1.day:02d}".format(y, dt)
    return date_str, time_str


class ArticleInfo(typing.NamedTuple):
    number: int
    subject: str
    from_: str
    date: datetime.datetime
    message_id: str
    references: str
    bytes: int
    lines: int
    headers: dict[str, str]

    def __str__(self) -> str:
        return "\t".join(
            [
                str(self.number),
                self.subject,
                self.from_,
                email.utils.format_datetime(self.date),
                self.message_id,
                self.references,
                str(self.bytes),
                str(self.lines),
            ]
            + [f"{k}: {v}" for k, v in self.headers.items()]
        )


class Article(typing.NamedTuple):
    info: ArticleInfo
    body: str


class NNTPGroup(abc.ABC):
    @property
    @abc.abstractmethod
    def name(self) -> str:
        ...

    @property
    @abc.abstractmethod
    def short_description(self) -> str:
        ...

    @property
    @abc.abstractmethod
    def number(self) -> int:
        ...

    @property
    @abc.abstractmethod
    def low(self) -> int:
        ...

    @property
    @abc.abstractmethod
    def high(self) -> int:
        ...

    @property
    @abc.abstractmethod
    def articles(self) -> typing.Dict[int, ArticleInfo]:
        ...


class NNTPServer(abc.ABC, socketserver.TCPServer):
    overview_format: typing.List[str] = _DEFAULT_OVERVIEW_FMT

    @property
    @abc.abstractmethod
    def groups(self) -> typing.Dict[str, NNTPGroup]:
        ...

    @property
    @abc.abstractmethod
    def articles(self) -> typing.Dict[int, ArticleInfo]:
        ...

    @abc.abstractmethod
    def article(self, key: typing.Union[str, int]) -> Article:
        ...


class NNTPConnectionHandler(socketserver.BaseRequestHandler):
    """
    The request handler class for our server.

    It is instantiated once per connection to the server, and must
    override the handle() method to implement communication to the
    client.
    """

    server: NNTPServer

    def __init__(self, *args, debugging=True, **kwargs):
        print("NEW connection.")
        self.command_queue = collections.deque()
        self.command_history: typing.List[str] = []
        self._init: bool = True
        self._quit: bool = False
        self.debugging: bool = debugging
        self.current_selected_newsgroup = None
        self.current_article_number: int = None
        super().__init__(*args, **kwargs)

    def handle(self):
        print("HADNLE")
        if self._quit:
            raise Exception("QUIT??")
        if self._init:
            self.send_lines(["201 NNTP Service Ready, posting prohibited"])
            self._init = False
        # self.request is the TCP socket connected to the client
        while True:
            self.data = self.request.recv(_MAXLINE).strip().decode("ascii")
            if self.debugging:
                print("got:", self.data)
            if self.data == "CAPABILITIES":
                self.capabilities()
            elif self.data.startswith("GROUP"):
                _, group_name = self.data.split()
                self.select_group(group_name)
            elif self.data.startswith("OVER") or self.data.startswith("XOVER"):
                self.overview(self.data)
            elif self.data.startswith("STAT"):
                self.stat(self.data)
            elif self.data.startswith("ARTICLE"):
                self.article(self.data)
            elif self.data.startswith("HEAD"):
                self.head(self.data)
            elif self.data == "LIST NEWSGROUPS":
                self.list(keyword="NEWSGROUPS")
            elif self.data == "MODE READER":
                self.send_lines(["201 NNTP Service Ready, posting prohibited"])
            elif self.data == "LIST OVERVIEW.FMT":
                self.send_lines(
                    ["215 Order of fields in overview database."]
                    + self.server.overview_format
                    + ["."]
                )
            elif self.data == "QUIT":
                self._quit = True
                self.send_lines(["205 Connection closing"])
            elif self.data == "":
                break
            else:
                self.send_lines(["500 Unknown command"])
                return
            self.command_history.append(self.data)

    def capabilities(self):
        self.send_lines(
            [
                "101 Capability list:",
                "VERSION 2",
                "READER",
                "LIST ACTIVE NEWSGROUPS OVERVIEW.FMT HEADERS",
                "OVER",
                ".",
            ]
        )

    def list(
        self,
        keyword: typing.Union[str, None] = None,
        argument: typing.Union[str, None] = None,
        wildmat: typing.Union[str, None] = None,
    ):
        if keyword == "ACTIVE" or keyword is None:
            if argument is None and wildmat is None:
                self.send_lines(
                    ["215 list of newsgroups follows"]
                    + [
                        f"{g.name} {g.high} {g.low} n"
                        for g in self.server.groups.values()
                    ]
                    + ["."]
                )
                return
        if keyword == "NEWSGROUPS":
            if argument is None and wildmat is None:
                self.send_lines(
                    ["215 list of newsgroups follows"]
                    + [
                        f"{g.name}\t{g.short_description}"
                        for g in self.server.groups.values()
                    ]
                    + ["."]
                )
                return

        self.send_lines(["501 Syntax Error"])
        return

    def select_group(self, group_name: str):
        print("Group name", group_name)
        if group_name in self.server.groups:
            self.current_selected_newsgroup = group_name
            group = self.server.groups[group_name]
            self.send_lines(
                [f"211 {group.number} {group.low} {group.high} {group.name}"]
            )
        else:
            self.send_lines(["411 No such newsgroup"])

    def send_lines(self, lines: typing.List[str]):
        for line in lines:
            if self.debugging:
                print("sending", line)
            self.request.sendall(bytes(line.strip(), "utf-8") + _CRLF)

    def overview(self, command: str):
        if self.current_selected_newsgroup is None:
            self.send_lines(["412 No newsgroups elected"])
            return
        self.send_lines(
            ["224 Overview information follows (multi-line)"]
            + list(map(str, self.server.articles))
            + ["."]
        )

    def stat(self, command: str):
        command, *tokens = command.split()
        if len(tokens) == 0:
            if self.current_selected_newsgroup is None:
                self.send_lines(["412 No newsgroup elected"])
                return
            if self.current_article_number is None:
                self.send_lines(["420 Current article number is invalid"])
                return
            article = self.server.articles[self.current_article_number]
        else:
            article = self.server.articles[int(tokens[0])]

        self.send_lines([f"223 {article.number} {article.message_id}"])
        return

    def article(self, command: str):
        command, *tokens = command.split()
        if len(tokens) == 0:
            if self.current_selected_newsgroup is None:
                self.send_lines(["412 No newsgroup elected"])
                return
            if self.current_article_number is None:
                self.send_lines(["420 Current article number is invalid"])
                return
            article = self.server.article(self.current_article_number)
        else:
            try:
                article = self.server.article(int(tokens[0]))
            except:
                article = self.server.article(tokens[0])

        ret = [
            f"220 {article.info.number} {article.info.message_id}",
            f"From: <{article.info.from_}>",
            f"Subject: {article.info.subject}",
            f"Date: {email.utils.format_datetime(article.info.date)}",
            f"Message-ID: {article.info.message_id}",
        ]
        if article.info.references:
            ret.append(f"References: {article.info.references}")
        ret += [f"{k}: {v}" for k, v in article.info.headers.items()]

        ret.append("")
        for line in article.body.split("\n"):
            ret.append(line)
        ret += ["."]
        self.send_lines(ret)

    def head(self, command: str):
        command, *tokens = command.split()
        if len(tokens) == 0:
            if self.current_selected_newsgroup is None:
                self.send_lines(["412 No newsgroup elected"])
                return
            if self.current_article_number is None:
                self.send_lines(["420 Current article number is invalid"])
                return
            article = self.server.article(self.current_article_number)
        else:
            try:
                article = self.server.article(int(tokens[0]))
            except:
                article = self.server.article(tokens[0])

        ret = [
            f"221 {article.info.number} {article.info.message_id}",
            f"From: <{article.info.from_}>",
            f"Subject: {article.info.subject}",
            f"Date: {email.utils.format_datetime(article.info.date)}",
            f"Message-ID: {article.info.message_id}",
        ]
        if article.info.references:
            ret.append(f"References: {article.info.references}")
        ret += [f"{k}: {v}" for k, v in article.info.headers.items()]
        ret += ["."]
        self.send_lines(ret)
