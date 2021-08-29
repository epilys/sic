from multiprocessing import Process, Queue
import queue
import subprocess
from datetime import datetime
from pathlib import Path
import urllib

from django.core.management.base import BaseCommand
from django.db import connections
from django.utils.timezone import make_aware
from django.apps import apps

config = apps.get_app_config("sic")
from sic.models import Story, StoryRemoteContent
from sic.search import index_story

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent


def f(qin, qout):
    try:
        (pk, url) = qin.get(timeout=5)
        if url is None or len(url) == 0:
            return f(qin, qout)
        with urllib.request.urlopen(
            urllib.request.Request(
                url,
                data=None,
                headers={},
                origin_req_host=None,
                unverifiable=False,
                method="GET",
            )
        ) as response:
            if not response.getheader("Content-Type").startswith("text/html"):
                return f(qin, qout)
        with subprocess.Popen(
            [
                BASE_DIR
                / "tools/fetch_remote_content/target/debug/fetch_remote_content",
                url,
            ],
            stdout=subprocess.PIPE,
        ) as proc:
            content = proc.stdout.read().decode("utf-8")
            qout.put((pk, url, content, datetime.now()))
    except Exception as exc:
        pass
    return


class Command(BaseCommand):
    help = "Fetch remote content"

    def handle(self, *args, **kwargs):
        stories = Story.objects.filter(remote_content=None, url__isnull=False)
        count = stories.count()
        if count == 0:
            return
        if count > 10:
            count = 10
        qin = Queue()
        qout = Queue()
        stories = {s.pk: s for s in stories}
        for k in stories:
            qin.put((k, stories[k].url))
        procs = []
        for num in range(count):
            proc = Process(target=f, args=(qin, qout))
            proc.start()
            procs.append(proc)

        for p in procs:
            p.join(5)

        while not qout.empty():
            pk, url, content, date = qout.get()
            StoryRemoteContent(
                story=stories[pk],
                url=url,
                content=content,
                retrieved_at=make_aware(date),
            ).save()
            index_story(stories[pk])
