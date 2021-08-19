import subprocess
import types
from datetime import datetime
from pathlib import Path
import urllib
import enum
import logging
from django.db import models
from django.utils.timezone import make_aware
from django.utils.module_loading import import_string
from sic.models import Story, StoryRemoteContent
from sic.mail import Digest
from sic.search import index_story

BASE_DIR = Path(__file__).resolve().parent.parent


def send_digests(input_):
    Digest.send_digests()


def fetch_url(input_):
    try:
        pk = input_["pk"]
        url = input_["url"]
        if pk is None or url is None or len(url) == 0:
            return None
        with urllib.request.urlopen(
            urllib.request.Request(
                url,
                method="GET",
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_4) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.163 Safari/537.36",
                },
            ),
            timeout=3,
        ) as response:
            if not "text/html" in response.getheader("Content-Type"):
                return f"""Content-Type is {response.getheader("Content-Type")}"""
        with subprocess.Popen(
            [
                BASE_DIR
                / "tools/fetch_remote_content/target/debug/fetch_remote_content",
                url,
            ],
            stdout=subprocess.PIPE,
        ) as proc:
            content = proc.stdout.read().decode("utf-8")
            StoryRemoteContent(
                story_id=pk,
                url=url,
                content=content,
                retrieved_at=make_aware(datetime.now()),
            ).save()
            index_story(Story.objects.get(pk=pk))
            return True
    except Exception as exc:
        logging.exception(f"Could not fetch url: {exc}")
        raise exc
    return None


class JobKind(models.Model):
    id = models.AutoField(primary_key=True)
    dotted_path = models.TextField(null=False, blank=False, unique=True)
    created = models.DateTimeField(auto_now_add=True, null=False, blank=False)
    last_modified = models.DateTimeField(auto_now_add=True, null=False, blank=False)

    def __str__(self):
        return self.dotted_path

    def from_func(func):
        logging.info("jobkind frm func", func)
        if isinstance(func, types.FunctionType):
            dotted_path = f"{func.__module__}.{func.__name__}"
            ret, _ = JobKind.objects.get_or_create(dotted_path=dotted_path)
            return ret
        else:
            raise TypeError

    def run(self, data):
        logging.info("jobkind run")
        try:
            func = import_string(self.dotted_path)
            return func(data)
        except ImportError:
            logging.error(f"Could not resolve job dotted_path: {self.dotted_path}")
            raise ImportError


class Job(models.Model):
    id = models.AutoField(primary_key=True)
    kind = models.ForeignKey(JobKind, null=True, on_delete=models.SET_NULL)
    created = models.DateTimeField(auto_now_add=True)
    active = models.BooleanField(default=True, null=False, blank=False)
    periodic = models.BooleanField(default=False, null=False, blank=False)
    failed = models.BooleanField(default=False, null=False, blank=False)
    last_run = models.DateTimeField(default=None, null=True, blank=True)
    logs = models.TextField(null=True, blank=True)
    data = models.JSONField(null=True, blank=True)

    def __str__(self):
        return f"{self.kind} {self.data}"

    def run(self):
        if not self.kind_id:
            return
        self.last_run = make_aware(datetime.now())
        try:
            res = self.kind.run(self.data)
            if res and not self.periodic:
                self.active = False
            if isinstance(res, str):
                self.logs += res
            self.failed = False
            self.save(update_fields=["last_run", "failed", "active", "logs"])
        except Exception as exc:
            if self.logs is None:
                self.logs = ""
            self.logs += str(exc)
            self.failed = True
            self.save(update_fields=["last_run", "failed", "logs"])
        return
