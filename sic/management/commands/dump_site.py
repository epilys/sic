from django.core.management.base import BaseCommand
from django.core.serializers import serialize
from sic.models import *
import json


class Command(BaseCommand):
    help = "Dump stories, users, tags to a JSON file for easy import into a new development environment"

    def add_arguments(self, parser):
        parser.add_argument(
            "output-file", type=str, help="path where output will be written"
        )

    def handle(self, *args, **kwargs):
        filename = kwargs["output-file"]
        print(f"Dumping data to {filename}")

        json_stories = json.loads(serialize("json", Story.objects.all()))
        json_users = json.loads(serialize("json", User.objects.all()))
        json_tags = json.loads(serialize("json", Tag.objects.all()))

        print(
            f"Preparing to write {len(json_stories)} stories, {len(json_users)} users, and {len(json_tags)} tags."
        )

        for s in json_stories:
            story = Story.objects.get(pk=s["pk"])
            s["fields"]["tags"] = list(map(lambda m: m.name, story.tags.all()))
            print(f"tags: {s['fields']['tags']}")
            s["fields"]["user"] = story.user.username

        for t in json_tags:
            tag = Tag.objects.get(pk=t["pk"])
            t["fields"]["parents"] = list(map(lambda m: m.name, tag.parents.all()))

        stories = list(map(lambda s: s["fields"], json_stories))
        users = list(map(lambda u: u["fields"], json_users))
        tags = list(map(lambda t: t["fields"], json_tags))

        dump = {}
        dump["Stories"] = stories
        dump["Users"] = users
        dump["Tags"] = tags

        open(filename, "w").write(json.dumps(dump))
