from django.contrib import admin
from django.contrib.auth.models import Permission
from django.forms import ModelForm
from django.forms.widgets import TextInput
from django.utils.safestring import mark_safe
from sic.models import *
from sic.mail import Digest
from sic.moderation import ModerationLogEntry
from sic.jobs import Job, JobKind
from sic.webmention import Webmention
from sic.flatpages import DocumentationFlatPage, CommunityFlatPage, ExternalLinkFlatPage


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
    def tags_html(self, obj):
        if not obj.tags.exists():
            return "-"
        return ",".join(list(map(lambda t: str(t), obj.tags.all())))

    def kind_html(self, obj):
        if not obj.kind.exists():
            return "-"
        return ",".join(list(map(lambda k: str(k), obj.kind.all())))

    ordering = ["-created", "title"]
    list_display = [
        "title",
        "user",
        "kind_html",
        "tags_html",
        "created",
        "url",
        "last_modified",
        "karma",
        "message_id",
    ]
    list_filter = [
        "tags",
        "kind",
        "active",
    ]


class CommentAdmin(ModelAdmin):
    ordering = ["-created"]
    list_display = [
        "user",
        "story",
        "parent",
        "created",
        "text",
        "last_modified",
        "karma",
        "message_id",
    ]


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


class TaggregationHasTagInline(admin.TabularInline):
    model = TaggregationHasTag


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
    inlines = [
        TaggregationHasTagInline,
    ]


@admin.action(description="Validate email addresses")
def validate_emails(modeladmin, request, queryset):
    for user in queryset.all():
        user.email_validated = True
        user.save(update_fields=["email_validated"])


class UserAdmin(ModelAdmin):
    ordering = ["-created"]

    def username_or_email(self, obj):
        if obj.username:
            return obj.username
        return obj.email

    list_display = [
        "username_or_email",
        "email",
        "created",
        "last_login",
        "can_participate",
        "email_validated",
        "is_active",
        "is_admin",
        "is_moderator",
    ]
    list_filter = ["is_active", "email_validated", "is_admin", "is_moderator"]
    actions = [validate_emails]


class VoteAdmin(ModelAdmin):
    ordering = ["-created"]
    list_display = ["user", "story", "comment", "created"]


class DomainAdmin(ModelAdmin):
    list_display = ["url"]


class StoryKindAdmin(ModelAdmin):
    ordering = ["name", "created"]
    list_display = ["name", "hex_color_html", "created"]


class InvitationRequestVoteInline(admin.TabularInline):
    model = InvitationRequestVote


class InvitationRequestAdmin(ModelAdmin):
    ordering = ["-created"]
    list_display = ["name", "address", "created"]
    inlines = [InvitationRequestVoteInline]


class StoryFilterAdmin(ModelAdmin):
    ordering = ["name"]


class ExactTagFilterAdmin(StoryFilterAdmin):
    list_display = ["name", "tag"]


class UserFilterAdmin(StoryFilterAdmin):
    list_display = ["name", "user"]


class MatchFilterAdmin(StoryFilterAdmin):
    list_display = ["name", "match_string", "is_regexp"]


class TagNameFilterAdmin(MatchFilterAdmin):
    pass


class DomainFilterAdmin(MatchFilterAdmin):
    pass


class DigestAdmin(ModelAdmin):
    ordering = ["-id"]
    list_display = ["user", "active", "all_stories", "last_run"]


class StoryRemoteContentAdmin(ModelAdmin):
    ordering = ["-retrieved_at"]
    list_display = ["story", "url", "retrieved_at"]


class TaggregationHasTagAdmin(ModelAdmin):
    ordering = ["-id"]
    list_display = ["taggregation", "tag", "depth"]


class ModerationLogEntryAdmin(ModelAdmin):
    ordering = ["-action_time"]
    list_display = [
        "action_time",
        "user",
        "action",
        "reason",
        "content_type",
        "is_public",
        "change_is_public",
    ]
    list_filter = ["user", "content_type", "is_public"]


class WebmentionAdmin(ModelAdmin):
    ordering = ["-created"]
    list_display = ["story", "url", "created", "was_received"]


@admin.action(description="Run jobs")
def run_jobs(modeladmin, request, queryset):
    for job in queryset.all():
        job.run()


class ArticleAdmin(admin.ModelAdmin):
    list_display = ["title", "status"]
    ordering = ["title"]


class JobAdmin(ModelAdmin):
    def success(self, obj):
        if obj.last_run is None:
            return None
        return not obj.failed

    readonly_fields = (
        "json_pprint",
        "message",
    )

    @admin.display(description="JSON pretty print")
    def json_pprint(self, instance):
        import json

        return mark_safe(
            f"""<pre>{json.dumps(instance.data, sort_keys=True, indent=4)}</pre>"""
        )

    @admin.display(description="Message")
    def message(self, instance):
        import email
        from email.policy import default as email_policy

        try:
            msg = email.message_from_string(instance.data, policy=email_policy)
        except Exception as exc:
            return mark_safe(f"Could not parse email: {exc}")

        headers = ""
        for h in msg:
            headers += f"{h}: {str(msg[h])}\n"
        body = msg.get_body(preferencelist=("markdown", "plain", "html"))  # type: ignore
        text = body.get_content().strip()
        return mark_safe(
            f"""<pre>{headers}

{text}</pre>"""
        )

    success.boolean = True
    ordering = ["-created", "-last_run"]
    actions = [run_jobs]
    list_display = ["__str__", "created", "active", "periodic", "success", "last_run"]
    list_filter = [
        "kind",
        "active",
        "failed",
    ]


class JobKindAdmin(ModelAdmin):
    def resolves(self, obj):
        from django.utils.module_loading import import_string

        try:
            _ = import_string(obj.dotted_path)
            return True
        except ImportError:
            return False

    resolves.boolean = True
    ordering = ["-created", "-last_modified"]
    list_display = ["__str__", "created", "last_modified", "resolves"]


admin.site.register(Comment, CommentAdmin)
admin.site.register(Digest, DigestAdmin)
admin.site.register(Domain, DomainAdmin)
admin.site.register(Hat, HatAdmin)
admin.site.register(Invitation, InvitationAdmin)
admin.site.register(Message, MessageAdmin)
admin.site.register(Moderation)
admin.site.register(Notification, NotificationAdmin)
admin.site.register(Story, StoryAdmin)
admin.site.register(StoryKind, StoryKindAdmin)
admin.site.register(StoryRemoteContent, StoryRemoteContentAdmin)
admin.site.register(Tag, TagAdmin)
admin.site.register(StoryFilter, StoryFilterAdmin)
admin.site.register(ExactTagFilter, ExactTagFilterAdmin)
admin.site.register(UserFilter, UserFilterAdmin)
admin.site.register(DomainFilter, DomainFilterAdmin)
admin.site.register(Taggregation, TaggregationAdmin)
admin.site.register(TaggregationHasTag, TaggregationHasTagAdmin)
admin.site.register(User, UserAdmin)
admin.site.register(Vote, VoteAdmin)
admin.site.register(ModerationLogEntry, ModerationLogEntryAdmin)
admin.site.register(InvitationRequest, InvitationRequestAdmin)
admin.site.register(Webmention, WebmentionAdmin)
admin.site.register(Job, JobAdmin)
admin.site.register(JobKind, JobKindAdmin)


class DocumentationFlatPageAdmin(ModelAdmin):
    ordering = ["order", "title"]
    list_display = ["title", "link_name", "order", "show_in_footer"]


class CommunityFlatPageAdmin(ModelAdmin):
    ordering = ["order", "title"]
    list_display = ["title", "link_name", "order", "show_inline", "show_in_footer"]


class ExternalLinkFlatPageAdmin(ModelAdmin):
    ordering = ["order", "title"]
    list_display = [
        "title",
        "link_name",
        "order",
        "external_url",
        "show_inline",
        "show_in_footer",
    ]


admin.site.register(DocumentationFlatPage, DocumentationFlatPageAdmin)
admin.site.register(CommunityFlatPage, CommunityFlatPageAdmin)
admin.site.register(ExternalLinkFlatPage, ExternalLinkFlatPageAdmin)


@admin.register(Permission)
class PermissionAdmin(ModelAdmin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("content_type")
