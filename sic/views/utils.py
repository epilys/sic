from http import HTTPStatus
from django.http import (
    HttpResponse,
)


def form_errors_as_string(errors):
    return ", ".join(
        map(lambda k: ", ".join(map(lambda err: k + ": " + err, errors[k])), errors)
    )


class HttpResponseNotImplemented(HttpResponse):
    status_code = HTTPStatus.NOT_IMPLEMENTED
