import subprocess
import types
from datetime import datetime, timedelta
from pathlib import Path
import urllib.request
import enum
import logging
import shlex
from django.db import models
from django.utils.timezone import make_aware
from django.utils.module_loading import import_string
from sic.models import Story, StoryRemoteContent
from sic.mail import Digest
from sic.search import index_story

BASE_DIR = Path(__file__).resolve().parent.parent


def send_digests(job):
    now = make_aware(datetime.now())
    if job.data:
        try:
            last_run = make_aware(datetime.fromtimestamp(job.data))
            if last_run and (now - last_run) <= timedelta(days=1):
                return
        except Exception as exc:
            print("send_digests() EXC ", exc)
    job.data = int(now.timestamp())
    job.save()
    Digest.send_digests()


def fetch_remote_content(url):
    with subprocess.Popen(
        [
            BASE_DIR / "tools/fetch_remote_content/target/debug/fetch_remote_content",
            url,
        ],
        stdout=subprocess.PIPE,
    ) as proc:
        content = proc.stdout.read().decode("utf-8")
    return content


def fetch_url(job):
    try:
        pk = job.data["pk"]
        url = job.data["url"]
        if pk is None or url is None or len(url) == 0:
            return None
        if url.startswith("gemini://"):
            content = fetch_remote_content(url)
            StoryRemoteContent(
                story_id=pk,
                url=url,
                content=content,
                retrieved_at=make_aware(datetime.now()),
            ).save()
            index_story(Story.objects.get(pk=pk))
            return True
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
            if "application/pdf" in response.getheader("Content-Type"):
                try:
                    from pdfminer.high_level import extract_pages
                    from pdfminer.layout import LTTextContainer
                except ImportError:
                    return f"""Content-Type is {response.getheader("Content-Type")} and could not import pdfminer.six"""
                from io import BytesIO, StringIO

                input_bytes = BytesIO(response.read())
                output_string = StringIO()
                # extract_text_to_fp(input_bytes, output_string)

                for page_layout in extract_pages(input_bytes):
                    for element in page_layout:
                        if isinstance(element, LTTextContainer):
                            output_string.write(element.get_text().strip())

                content = output_string.getvalue().strip()
                StoryRemoteContent(
                    story_id=pk,
                    url=url,
                    content=content,
                    retrieved_at=make_aware(datetime.now()),
                ).save()
                index_story(Story.objects.get(pk=pk))
                return True
            elif not "html" in response.getheader("Content-Type"):
                return f"""Content-Type is {response.getheader("Content-Type")}"""
            log = None
            content = fetch_remote_content(url)
            w3m_output = None
            try:
                w3m_output = subprocess.check_output(
                    f"curl -s {shlex.quote(url)} | w3m -T text/html -dump",
                    shell=True,
                ).decode("utf-8")
            except (subprocess.SubprocessError, UnicodeDecodeError) as exc:
                log = str(exc)
            StoryRemoteContent(
                story_id=pk,
                url=url,
                content=content,
                w3m_content=w3m_output,
                retrieved_at=make_aware(datetime.now()),
            ).save()
            index_story(Story.objects.get(pk=pk))
            return log if log else True
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

    @staticmethod
    def from_func(func):
        if isinstance(func, types.FunctionType):
            dotted_path = f"{func.__module__}.{func.__name__}"
            ret, _ = JobKind.objects.get_or_create(dotted_path=dotted_path)
            return ret
        else:
            raise TypeError

    def run(self, job):
        logging.info("jobkind run")
        try:
            func = import_string(self.dotted_path)
            return func(job)
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
            res = self.kind.run(self)
            if res and not self.periodic:
                self.active = False
            if isinstance(res, str):
                if self.logs is None:
                    self.logs = ""
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
