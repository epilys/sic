from django.contrib import admin
from django.contrib.auth.models import Permission
from django.forms import ModelForm
from django.forms.widgets import TextInput
from django.utils.safestring import mark_safe
from .models import *
from .moderation import ModerationLogEntry


def hex_color_html(self, obj):
    return mark_safe(
        f"<span style='background-color: {obj.hex_color}; height: 1rem; width: 1rem; display: inline-block;outline: 1px solid black;'></span> <code> {obj.hex_color}</code>"
    )


hex_color_html.short_description = "Hex Color"


class ModelAdmin(admin.ModelAdmin):
    save_on_top = True
    hex_color_html = hex_color_html


class TagForm(ModelForm):
    class Meta:
        model = Tag
        fields = "__all__"
        widgets = {
            "hex_color": TextInput(attrs={"type": "color"}),
        }


class TagAdmin(ModelAdmin):
    def parents_html(self, obj):
        if not obj.parents.exists():
            return "-"
        return ",".join(list(map(lambda p: str(p), obj.parents.all())))

    parents_html.short_description = "Parents"
    form = TagForm
    fieldsets = ((None, {"fields": ("name", "hex_color", "parents")}),)
    ordering = ["name", "created"]
    list_display = ["name", "hex_color_html", "parents_html", "created"]


class StoryAdmin(ModelAdmin):
    ordering = ["-created", "title"]
    list_display = ["title", "user", "created", "url"]
    list_filter = [
        "tags",
    ]


class CommentAdmin(ModelAdmin):
    ordering = ["-created"]
    list_display = ["user", "story", "parent", "created", "text"]


class HatAdmin(ModelAdmin):
    ordering = ["-last_modified"]
    list_display = ["name", "hex_color_html", "user", "created", "last_modified"]


class InvitationAdmin(ModelAdmin):
    ordering = ["-created", "-accepted"]
    list_display = ["inviter", "receiver", "address", "created"]
    list_filter = (("accepted", admin.EmptyFieldListFilter),)


class MessageAdmin(ModelAdmin):
    ordering = ["-created"]
    list_display = ["recipient", "read_by_recipient", "author", "created"]


class NotificationAdmin(ModelAdmin):
    ordering = ["-created"]
    list_display = ["name", "kind", "user"]
    list_filter = ["kind"]


class TaggregationAdmin(ModelAdmin):
    ordering = ["-created"]
    list_display = [
        "name",
        "description",
        "creator",
        "created",
        "last_modified",
        "default",
        "discoverable",
        "private",
    ]
    list_filter = ["default", "discoverable", "private"]


class UserAdmin(ModelAdmin):
    ordering = ["-created"]
    list_display = [
        "username",
        "email",
        "created",
        "is_active",
        "is_admin",
        "is_moderator",
    ]
    list_filter = ["is_active", "is_admin", "is_moderator"]


class VoteAdmin(ModelAdmin):
    ordering = ["-created"]
    list_display = ["user", "story", "comment", "created"]


class DomainAdmin(ModelAdmin):
    list_display = ["url"]


class StoryKindAdmin(ModelAdmin):
    ordering = ["name", "created"]
    list_display = ["name", "hex_color_html", "created"]


admin.site.register(Comment, CommentAdmin)
admin.site.register(Domain, DomainAdmin)
admin.site.register(Hat, HatAdmin)
admin.site.register(Invitation, InvitationAdmin)
admin.site.register(Message, MessageAdmin)
admin.site.register(Moderation)
admin.site.register(Notification, NotificationAdmin)
admin.site.register(Story, StoryAdmin)
admin.site.register(StoryKind, StoryKindAdmin)
admin.site.register(Tag, TagAdmin)
admin.site.register(TagFilter)
admin.site.register(Taggregation, TaggregationAdmin)
admin.site.register(User, UserAdmin)
admin.site.register(Vote, VoteAdmin)
admin.site.register(ModerationLogEntry)


@admin.register(Permission)
class PermissionAdmin(ModelAdmin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("content_type")
