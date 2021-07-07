"""
populate the app's current database with sample data from a json file
"""

from django.core.management.base import BaseCommand
from django.core.exceptions import ObjectDoesNotExist
from sic.models import *
import json


def user_from_dict(user_dict):
    user, _ = User.objects.get_or_create(username=user_dict["username"])
    # TODO: round trip groups and permissions later
    skip_attrs = ["groups", "user_permissions"]
    for k in user_dict.keys():
        if k not in skip_attrs:
            user.__setattr__(k, user_dict[k])
    return user


class Command(BaseCommand):
    help = "populate an empty database with some users, stories, comments and tags"

    def add_arguments(self, parser):
        parser.add_argument(
            "file",
            type=str,
            help="path to a file with JSON data to use to populate the site",
        )
        parser.add_argument(
            "--default-user",
            type=str,
            help="Local poster for any story where the user can't be found.",
            required=False,
        )

    def handle(self, *args, **kwargs):
        filename = kwargs["file"]

        print(f"Handling import from {filename}")
        objects = json.loads(open(filename, "r").read())

        # first import any users in the dump
        if "Users" in objects:
            users = objects["Users"]
            print(f"Creating {len(users)} users from JSON")
            for u in users:
                new_user = user_from_dict(u)
                new_user.save()

        # then choose a default user for any unrecognized author names in the export
        default_user = kwargs["default_user"]
        default_author = None
        if default_user is None:
            print(
                "No default user specified. Stories without a local author match will not be imported."
            )
        else:
            try:
                default_author = User.objects.get(username=default_user)
            except ObjectDoesNotExist:
                print(f"Unable to find {default_user} in local database. Aborting.")
                raise

        # import any tags in the dump and establish any exported parent relationships
        if "Tags" in objects:
            tags = objects["Tags"]
            for t in tags:
                new_tag, _ = Tag.objects.get_or_create(name=t["name"])
                if "hex_color" in t:
                    new_tag.hex_color = t["hex_color"]
                if "parents" in "t":
                    new_tag.save()
                    for p in t["parents"]:
                        new_parent, _ = Tag.objects.get_or_create(p)
                        new_tag.parents.add(new_parent)
                if "created" in t:
                    new_tag.created = t["created"]
                new_tag.save()

        # import any stories once tags and users are set up. absent users will be defaulted if possible, absent
        # tags will be created with no colors or parents
        if "Stories" in objects:
            stories = objects["Stories"]
            print(f"Creating {len(stories)} stories from JSON")
            for s in stories:
                try:
                    author = User.objects.get(username=s["user"])
                except ObjectDoesNotExist:
                    print(
                        f"author {s['user']} is not present locally. using {default_author}"
                    )
                    author = default_author
                new_story, _ = Story.objects.get_or_create(
                    user=author,
                    url=s["url"],
                    title=s["title"],
                    description=s["description"],
                    created=s["created"],
                    user_is_author=s["user_is_author"],
                    publish_date=s["publish_date"],
                )
                for t in s["tags"]:
                    new_tag, _ = Tag.objects.get_or_create(name=t)
                    new_story.tags.add(new_tag)
                new_story.save()
                print(f"Saved story '{new_story.title}' by '{new_story.user}'")

        # users = {
        #     "dummyuser": "dummyuser@example.com",
        #     "emailwithoutpassword": "user@example.com",
        #     "epilys": "epilys@uessuent.xyz",
        #     "bosmer": "bosmer@morriw.ind",
        # }
        # for i,u in enumerate(users.keys()):
        #     user = User(username=u, email=users[u])
        #     if not "withoutpassword" not in u:
        #         user.set_password(f"Change_me{i}!")
        #     print(f"Creating {str(user)}")
        #     user.save()
        # print(f"Creating tags")
        # print(f"Creating stories")
        # print(f"Creating comments")
        # print(f"Voting")
