from django.contrib import admin
from django.contrib.auth.models import Permission
from django.forms import ModelForm
from django.forms.widgets import TextInput
from .models import *


class TagForm(ModelForm):
    class Meta:
        model = Tag
        fields = "__all__"
        widgets = {
            "hex_color": TextInput(attrs={"type": "color"}),
        }


class TagAdmin(admin.ModelAdmin):
    form = TagForm
    fieldsets = ((None, {"fields": ("name", "hex_color", "parents")}),)


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
