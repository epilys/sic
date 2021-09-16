import json
import datetime
from django.contrib.contenttypes.models import ContentType
from django.db import models
from sic.models import User, Comment, Story, Tag


class ModerationLogEntry(models.Model):
    id = models.AutoField(primary_key=True)
    action_time = models.DateTimeField(
        auto_now_add=True,
        editable=False,
    )
    user = models.ForeignKey(
        User,
        models.SET_NULL,
        null=True,
    )
    action = models.TextField(null=False, blank=False)
    reason = models.TextField(null=False, blank=False)
    # change is either a string or a JSON structure
    change = models.TextField(null=True, blank=True)
    content_type = models.ForeignKey(
        ContentType, models.SET_NULL, verbose_name="content type", blank=True, null=True
    )
    object_id = models.TextField("object id", blank=True, null=True)
    is_public = models.BooleanField(null=False, default=True)
    change_is_public = models.BooleanField(null=False, default=True)

    class Meta:
        verbose_name = "moderation log entry"
        verbose_name_plural = "moderation log entries"
        ordering = ["-action_time"]

    def __repr__(self):
        return f"{self.action_time} {self.action}"

    def __str__(self):
        return f"{self.action_time} {self.user}: {self.action} {self.reason}"

    @staticmethod
    def edit_comment(before_text: str, comment_obj: Comment, user: User, reason):
        return ModerationLogEntry.objects.create(
            user=user,
            action="Edited comment",
            reason=reason,
            change=json.dumps(
                {
                    "before": before_text,
                    "after": comment_obj.text_to_plain_text,
                }
            ),
            content_type=ContentType.objects.get(app_label="sic", model="comment"),
            object_id=str(comment_obj.pk),
        )

    @staticmethod
    def delete_comment(comment_obj: Comment, user: User, reason):
        return ModerationLogEntry.objects.create(
            user=user,
            action="Deleted comment",
            reason=reason,
            content_type=ContentType.objects.get(app_label="sic", model="comment"),
            object_id=str(comment_obj.pk),
        )

    @staticmethod
    def edit_story_title(before_text: str, story_obj: Story, user: User, reason):
        return ModerationLogEntry.objects.create(
            user=user,
            action=f"Set story title to {story_obj.title}",
            reason=reason,
            change=json.dumps(
                {
                    "before": before_text,
                    "after": story_obj.title,
                }
            ),
            content_type=ContentType.objects.get(app_label="sic", model="story"),
            object_id=str(story_obj.pk),
        )

    @staticmethod
    def edit_story_desc(before_text: str, story_obj: Story, user: User, reason):
        return ModerationLogEntry.objects.create(
            user=user,
            action=f"Set story description to {story_obj.description}",
            reason=reason,
            change=json.dumps(
                {
                    "before": before_text,
                    "after": story_obj.description,
                }
            ),
            content_type=ContentType.objects.get(app_label="sic", model="story"),
            object_id=str(story_obj.pk),
        )

    @staticmethod
    def edit_story_url(before_text: str, story_obj: Story, user: User, reason):
        return ModerationLogEntry.objects.create(
            user=user,
            action=f"Set story url to {story_obj.url}",
            reason=reason,
            change=json.dumps(
                {
                    "before": before_text,
                    "after": story_obj.url,
                }
            ),
            content_type=ContentType.objects.get(app_label="sic", model="story"),
            object_id=str(story_obj.pk),
        )

    @staticmethod
    def edit_story_cw(before_text: str, story_obj: Story, user: User, reason):
        return ModerationLogEntry.objects.create(
            user=user,
            action=f"""Set story's content warning to "{story_obj.content_warning}" """,
            reason=reason,
            change=json.dumps(
                {
                    "before": before_text,
                    "after": story_obj.content_warning,
                }
            ),
            content_type=ContentType.objects.get(app_label="sic", model="story"),
            object_id=str(story_obj.pk),
        )

    @staticmethod
    def edit_story_pubdate(
        before_date: datetime.datetime, story_obj: Story, user: User, reason
    ):
        return ModerationLogEntry.objects.create(
            user=user,
            action=f"Set story's publish date to {story_obj.publish_date}",
            reason=reason,
            change=json.dumps(
                {
                    "before": before_date,
                    "after": story_obj.publish_date,
                }
            ),
            content_type=ContentType.objects.get(app_label="sic", model="story"),
            object_id=str(story_obj.pk),
        )

    @staticmethod
    def edit_story_tags(tags_before, story_obj: Story, user: User, reason):
        tags_after = list(story_obj.tags.all())
        return ModerationLogEntry.objects.create(
            user=user,
            action=f"""Edited story tags from ("{'", "'.join(t.name for t in tags_before)}") to ("{'", "'.join(t.name for t in tags_after)}")""",
            reason=reason,
            change=json.dumps(
                {
                    "before": [t.id for t in tags_before],
                    "after": [t.id for t in tags_after],
                }
            ),
            content_type=ContentType.objects.get(app_label="sic", model="story"),
            object_id=str(story_obj.pk),
        )

    @staticmethod
    def edit_story_kind(kinds_before, story_obj: Story, user: User, reason):
        kinds_after = list(story_obj.kind.all())
        return ModerationLogEntry.objects.create(
            user=user,
            action=f"""Edited story kind from ("{'", "'.join(k.name for k in kinds_before)}") to ("{'", "'.join(k.name for k in kinds_after)}")""",
            reason=reason,
            change=json.dumps(
                {
                    "before": [k.id for k in kinds_before],
                    "after": [k.id for k in kinds_after],
                }
            ),
            content_type=ContentType.objects.get(app_label="sic", model="story"),
            object_id=str(story_obj.pk),
        )

    @staticmethod
    def delete_story(story_obj: Story, user: User, reason):
        return ModerationLogEntry.objects.create(
            user=user,
            action="Deleted story",
            reason=reason,
            content_type=ContentType.objects.get(app_label="sic", model="story"),
            object_id=str(story_obj.pk),
        )

    @staticmethod
    def edit_tag_name(name_before: str, tag_obj: Tag, user: User, reason):
        return ModerationLogEntry.objects.create(
            user=user,
            action=f"""Edited tag name from "{name_before}" to "{tag_obj.name}" """,
            reason=reason,
            change=json.dumps(
                {
                    "before": name_before,
                    "after": tag_obj.name,
                }
            ),
            content_type=ContentType.objects.get(app_label="sic", model="tag"),
            object_id=str(tag_obj.pk),
        )

    @staticmethod
    def edit_tag_parents(parents_before, tag_obj: Tag, user: User, reason):
        parents_after = list(tag_obj.parents.all())
        return ModerationLogEntry.objects.create(
            user=user,
            action=f"""Edited tag parents from ("{'", "'.join(t.name for t in parents_before)}") to ("{'", "'.join(t.name for t in parents_after)}")""",
            reason=reason,
            change=json.dumps(
                {
                    "before": [t.id for t in parents_before],
                    "after": [t.id for t in parents_after],
                }
            ),
            content_type=ContentType.objects.get(app_label="sic", model="tag"),
            object_id=str(tag_obj.pk),
        )

    @staticmethod
    def create_tag(tag_obj: Tag, user: User):
        return ModerationLogEntry.objects.create(
            user=user,
            action=f"""Created tag: {tag_obj.name} with parents: ("{'", "'.join(t.name for t in tag_obj.parents.all())}")""",
            reason="",
            change="",
            content_type=ContentType.objects.get(app_label="sic", model="tag"),
            object_id=str(tag_obj.pk),
        )

    @staticmethod
    def changed_user_status(user_obj: User, user: User, action, reason):
        return ModerationLogEntry.objects.create(
            user=user,
            action=action,
            reason=reason,
            content_type=ContentType.objects.get(app_label="sic", model="user"),
            object_id=str(user_obj.pk),
        )

    @staticmethod
    def changed_story_status(story_obj: Story, user: User, action: str, reason: str):
        return ModerationLogEntry.objects.create(
            user=user,
            action=action,
            reason=reason,
            content_type=ContentType.objects.get(app_label="sic", model="story"),
            object_id=str(story_obj.pk),
        )

    def get_edited_object(self):
        if self.content_type and self.object_id:
            return self.content_type.get_object_for_this_type(pk=self.object_id)
        return None
