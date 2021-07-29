from bs4 import BeautifulSoup
import argparse
import sys
import re
import urllib.parse
import urllib.request
import http.cookiejar
from subprocess import Popen, PIPE

"""
Adapted from https://gist.github.com/epilys/b78fe285a2647ece8689f7c7c1bca90c

TODO: BeautifulSoup not needed, we can use python's HTMLParser instead.

default behaviours:

- looks for "vnu.jar" in PATH, but you can override that with --vnu-jar-bin flag.
- doesn't login, use --login with --username and --password for that
- doesn't check syndication feeds (rss, atom)

invocation: python3 tools/recursive_html_validate.py

usage: recursive_html_validate.py [-h] [--login] [--check-xml]
                                  [--vnu-jar-bin VNU_JAR_BIN] [-u USERNAME]
                                  [-p PASSWORD]
                                  url

positional arguments:
  url

optional arguments:
  -h, --help            show this help message and exit
  --login               login before scraping? (html and valid endpoints are
                        different when authenticated
  --check-xml           also check XML (feeds)
  --vnu-jar-bin VNU_JAR_BIN
  -u USERNAME, --username USERNAME
  -p PASSWORD, --password PASSWORD
"""

AUTHENTICATION_URL = "/admin/login/"
IGNORE_URLS = [
    "http",  # ignore external links
    "https",
    "mailto",
    "/save/",  # don't bookmark stories
    "/accounts/login",
]

VNU_REGEX = re.compile(
    r"^:(?P<first_line>\d*).(?P<first_col>\d*)-(?P<end_line>\d*).(?P<end_col>\d*): (?P<kind>[^:]*): (?P<message>.*)"
)


def scrape(
    username,
    password,
    vnu_jar_bin="vnu.jar",
    root_url="127.0.0.1:8002",
    page=None,
    depth=-1,
    _login=True,
    check_xml=False,
):
    ROOT_URL = root_url
    HTTP_ROOT_URL = "http://" + ROOT_URL
    CHECK_XML = check_xml
    VNU_CMD = [vnu_jar_bin, "-"]
    VNU_CMD_XML = [vnu_jar_bin, "--format", "xml", "-"]

    # username and password for login
    USERNAME = username
    PASSWORD = password
    # here goes URL that's found inside form action='.....'
    #   adjust as needed, can be all kinds of weird stuff

    # initiate the cookie jar (using : http.cookiejar and urllib.request)
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    urllib.request.install_opener(opener)
    urls = []

    def make_get(url):
        ####### change variables here, like URL, action URL, user, pass
        # your base URL here, will be used for headers and such, with and without https://
        base_url = ROOT_URL
        https_base_url = HTTP_ROOT_URL
        url = https_base_url + url

        ####### rest of the script is logic
        # but you will need to tweak couple things maybe regarding "token" logic
        #   (can be _token or token or _token_ or secret ... etc)

        # big thing! you need a referer for most pages! and correct headers are the key
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-agent": "Mozilla/5.0 Chrome/81.0.4044.92",  # Chrome 80+ as per web search
            "Host": base_url,
            "Origin": https_base_url,
            "Referer": https_base_url,
        }
        # first a simple request, just to get login page and parse out the token
        #       (using : urllib.request)
        request = urllib.request.Request(url)
        response = urllib.request.urlopen(request)
        contents = response.read()

        html = contents.decode("utf-8")
        return html

    def make_post(url, payload):
        ####### change variables here, like URL, action URL, user, pass
        # your base URL here, will be used for headers and such, with and without https://
        base_url = ROOT_URL
        https_base_url = HTTP_ROOT_URL
        url = https_base_url + url

        ####### rest of the script is logic
        # but you will need to tweak couple things maybe regarding "token" logic
        #   (can be _token or token or _token_ or secret ... etc)

        # big thing! you need a referer for most pages! and correct headers are the key
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-agent": "Mozilla/5.0 Chrome/81.0.4044.92",  # Chrome 80+ as per web search
            "Host": base_url,
            "Origin": https_base_url,
            "Referer": https_base_url,
        }
        # first a simple request, just to get login page and parse out the token
        #       (using : urllib.request)
        request = urllib.request.Request(url)
        response = urllib.request.urlopen(request)
        contents = response.read()

        # parse the page, we look for token eg. on my page it was something like this:
        #    <input type="hidden" name="_token" value="random1234567890qwertzstring">
        #       this can probably be done better with regex and similar
        #       but I'm newb, so bear with me
        html = contents.decode("utf-8")
        # text just before start and just after end of your token string
        mark_start = '<input type="hidden" name="csrfmiddlewaretoken" value="'
        mark_end = '">'
        # index of those two points
        start_index = html.find(mark_start) + len(mark_start)
        end_index = html.find(mark_end, start_index)
        # and text between them is our token, store it for second step of actual login
        token = html[start_index:end_index]

        # here we craft our payload, it's all the form fields, including HIDDEN fields!
        #   that includes token we scraped earler, as that's usually in hidden fields
        #   make sure left side is from "name" attributes of the form,
        #       and right side is what you want to post as "value"
        #   and for hidden fields make sure you replicate the expected answer,
        #       eg. "token" or "yes I agree" checkboxes and such

        payload["csrfmiddlewaretoken"] = token

        # now we prepare all we need for login
        #   data - with our payload (user/pass/token) urlencoded and encoded as bytes
        data = urllib.parse.urlencode(payload)
        binary_data = data.encode("UTF-8")
        # and put the URL + encoded data + correct headers into our POST request
        #   btw, despite what I thought it is automatically treated as POST
        #   I guess because of byte encoded data field you don't need to say it like this:
        #       urllib.request.Request(authentication_url, binary_data, headers, method='POST')
        request = urllib.request.Request(url, binary_data, headers)
        response = urllib.request.urlopen(request)
        contents = response.read()
        contents = contents.decode("utf-8")
        return contents

    def login():
        login_data = {
            #'name':'value',    # make sure this is the format of all additional fields !
            "username": USERNAME,
            "password": PASSWORD,
            "next": "/",
        }
        contents = make_post(AUTHENTICATION_URL, login_data)

    def rec_scrape(site, depth):
        if depth == 0:
            return
        try:
            r = make_get(site)
        except Exception as exc:
            print(site, exc, file=sys.stderr)
            return False
        source_lines = r.splitlines()
        print(HTTP_ROOT_URL + site)
        vnu_cmd = VNU_CMD
        if site.endswith(".rss") or site.endswith(".atom"):
            if not CHECK_XML:
                print(site, "check_xml is false, ignoring", file=sys.stderr)
                return
            vnu_cmd = VNU_CMD_XML
        with Popen(vnu_cmd, stdin=PIPE, stderr=PIPE) as proc:
            outs, errors = proc.communicate(input=bytes(r, "utf-8"))
            errors = errors.decode("utf-8")
        for line in errors.splitlines():
            for match in VNU_REGEX.finditer(line):
                d = match.groupdict()
                padding = max(len(d["first_line"]), len(d["end_line"]))
                start = int(d["first_line"])
                if start > 2:
                    start -= 2
                else:
                    start = 0
                end = int(d["end_line"]) + 1
                if end + 2 < len(source_lines):
                    end += 2
                else:
                    end = len(source_lines)
                print(d["kind"], d["message"])
                print()
                for l in range(start, end):
                    if l >= int(d["first_line"]) and l <= int(d["end_line"]):
                        print(
                            " " * (padding - len(str(l))),
                            l,
                            "*| ",
                            source_lines[l + 1][:80],
                        )
                    else:
                        print(
                            " " * (padding - len(str(l))),
                            l,
                            " | ",
                            source_lines[l + 1][:80],
                        )
                print()
        s = BeautifulSoup(r, "html.parser")

        for i in s.find_all("a"):
            href = i.attrs["href"]
            if href.startswith("/"):
                site = href
                if site not in urls:
                    ignore = False
                    for ignore_url in IGNORE_URLS:
                        ignore |= site.startswith(ignore_url)
                    if ignore:
                        continue
                    urls.append(site)
                    rec_scrape(site, depth - 1)
        return True

    if _login:
        login()
    if page is None:
        page = "/"
    rec_scrape(page, depth)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="")
    parser.add_argument("url", type=str, help="")
    parser.add_argument("--page", type=str, help="", required=False, default=None)
    parser.add_argument("--depth", type=int, help="", required=False, default=-1)
    parser.add_argument(
        "--login",
        action="store_true",
        default=False,
        help="login before scraping? (html and valid endpoints are different when authenticated",
    )
    parser.add_argument(
        "--check-xml",
        action="store_true",
        default=False,
        help="also check XML (feeds)",
    )
    parser.add_argument("--vnu-jar-bin", type=str, default="vnu.jar")
    parser.add_argument("-u", "--username", type=str, default=None)
    parser.add_argument("-p", "--password", type=str, default=None)

    args = parser.parse_args()

    scrape(
        args.username,
        args.password,
        vnu_jar_bin=args.vnu_jar_bin,
        root_url=args.url,
        page=args.page,
        depth=args.depth,
        _login=args.login,
        check_xml=args.check_xml,
    )
