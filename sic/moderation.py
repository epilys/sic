from django.contrib.contenttypes.models import ContentType
from django.db import models
from .models import User, Comment, Story

import json


class ModerationLogEntry(models.Model):
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
        return f"{self.action_time} {self.user}: {self.action}"

    @staticmethod
    def edit_comment(before_text: str, comment_obj: Comment, user: User, reason):
        return ModerationLogEntry.objects.create(
            user=user,
            action="Edited comment",
            reason=reason,
            change=json.dumps(
                {
                    "before": before_text,
                    "after": comment_obj.text_to_plain_text(),
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
            action="Edited story title",
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
            action="Edited story description",
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
            action="Edited story url",
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
    def delete_story(story_obj: Story, user: User, reason):
        return ModerationLogEntry.objects.create(
            user=user,
            action="Deleted story",
            reason=reason,
            content_type=ContentType.objects.get(app_label="sic", model="story"),
            object_id=str(story_obj.pk),
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

    def get_edited_object(self):
        if self.content_type and self.object_id:
            return self.content_type.get_object_for_this_type(pk=self.object_id)
        return None
