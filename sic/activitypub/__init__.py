from django.urls import path
from ..apps import SicAppConfig as config
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_http_methods
from django.contrib.sites.models import Site

import functools


@functools.lru_cache(maxsize=None)
def pub_key():
    return open(config.AP_PUBKEY_PATH, "r").read().replace("\n", r"\n")


def actor_id(request):
    domain = Site.objects.get_current().domain
    return JsonResponse(
        {
            "@context": [
                "https://www.w3.org/ns/activitystreams",
                "https://w3id.org/security/v1",
            ],
            "id": f"http://{domain}/activity-pub/id.json",
            "type": "Person",
            "preferredUsername": "sic",
            "inbox": f"http://{domain}/activity-pub/inbox.json",
            "publicKey": {
                "id": f"http://{domain}/activity-pub/id.json#main-key",
                "owner": f"http://{domain}/activity-pub/id.json",
                "publicKeyPem": pub_key(),
            },
        }
    )


@require_http_methods(["GET"])
def inbox_id(request):
    return JsonResponse({})


urlpatterns = [
    path("id.json", actor_id, name="ap_actor_id"),
    path("inbox.json", inbox_id, name="ap_inbox_id"),
]
