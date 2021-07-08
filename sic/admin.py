from django.contrib import admin
from django.contrib.auth.models import Permission
from django.forms import ModelForm
from django.forms.widgets import TextInput
from django.utils.safestring import mark_safe
from .models import *


class TagForm(ModelForm):
    class Meta:
        model = Tag
        fields = "__all__"
        widgets = {
            "hex_color": TextInput(attrs={"type": "color"}),
        }


class TagAdmin(admin.ModelAdmin):
    def hex_color_html(self, obj):
        return mark_safe(
            f"<span style='background-color: {obj.hex_color}; height: 1rem; width: 1rem; display: inline-block;outline: 1px solid black;'></span> <code> {obj.hex_color}</code>"
        )

    hex_color_html.short_description = "Hex Color"

    def parents_html(self, obj):
        if not obj.parents.exists():
            return "-"
        return ",".join(list(map(lambda p: str(p), obj.parents.all())))

    parents_html.short_description = "Parents"
    form = TagForm
    fieldsets = ((None, {"fields": ("name", "hex_color", "parents")}),)
    ordering = ["name", "created"]
    list_display = ["name", "hex_color_html", "parents_html", "created"]


admin.site.register(Comment)
admin.site.register(Domain)
admin.site.register(Hat)
admin.site.register(Invitation)
admin.site.register(Message)
admin.site.register(Moderation)
admin.site.register(Story)
admin.site.register(Tag, TagAdmin)
admin.site.register(TagFilter)
admin.site.register(User)
admin.site.register(Vote)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("content_type")
