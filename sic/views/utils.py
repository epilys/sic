import ipaddress
import socket
import re
import urllib.parse
from http import HTTPStatus
from django.http import (
    HttpResponse,
)
from django.core.paginator import Paginator as PaginatorDjango, InvalidPage


def form_errors_as_string(errors):
    return ", ".join(
        map(lambda k: ", ".join(map(lambda err: k + ": " + err, errors[k])), errors)
    )


class HttpResponseNotImplemented(HttpResponse):
    status_code = HTTPStatus.NOT_IMPLEMENTED


class Paginator(PaginatorDjango):
    def get_elided_page_range(self, number=1, *, on_each_side=3, on_ends=2):
        """
        Return a 1-based range of pages with some values elided.
        If the page range is larger than a given size, the whole range is not
        provided and a compact form is returned instead, e.g. for a paginator
        with 50 pages, if page 43 were the current page, the output, with the
        default arguments, would be:
            1, 2, …, 40, 41, 42, 43, 44, 45, 46, …, 49, 50.
        """
        number = self.validate_number(number)

        if self.num_pages <= (on_each_side + on_ends) * 2:
            yield from self.page_range
            return

        if number > (1 + on_each_side + on_ends) + 1:
            yield from range(1, on_ends + 1)
            yield None
            yield from range(number - on_each_side, number + 1)
        else:
            yield from range(1, number + 1)

        if number < (self.num_pages - on_each_side - on_ends) - 1:
            yield from range(number + 1, number + on_each_side + 1)
            yield None
            yield from range(self.num_pages - on_ends + 1, self.num_pages + 1)
        else:
            yield from range(number + 1, self.num_pages + 1)


def check_safe_url(url):
    if url is not None:
        url = url.strip()

    if not url:
        return False
    if url.startswith("///"):
        return False

    if not re.search(r"^[a-zA-Z0-9+.\-]+://", url):
        url = "//" + url
    try:
        urlparse = urllib.parse.urlparse(url)
    except ValueError:
        return False

    if not urlparse.netloc and urlparse.scheme:
        return False
    if not urlparse.scheme and urlparse.netloc:
        scheme = "http"
    else:
        scheme = urlparse.scheme

    netloc, *port = urlparse.netloc.split(sep=":", maxsplit=1)

    if netloc == "localhost":
        return False

    try:
        ip = ipaddress.ip_address(netloc)
        if not ip.is_global:
            return False
    except ValueError:
        pass

    if len(port) == 0:
        if scheme == "http":
            port = 80
        elif scheme == "https":
            port = 443
        elif scheme == "gemini":
            port = 1965
        else:
            return False
    elif len(port) != 1:
        return False
    else:
        port = port[0]

    try:
        addrinfos = socket.getaddrinfo(netloc, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    if len(addrinfos) == 0:
        return False
    for addrinfo in addrinfos:
        _, _, _, _, (ip, *_rest) = addrinfo
        try:
            ip = ipaddress.ip_address(ip)
            if not ip.is_global:
                return False
        except ValueError:
            return False
    return True


next_re = re.compile(r"^/[^/]")


def check_next_url(next):
    return next_re.search(next) is not None
