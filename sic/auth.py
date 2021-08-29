from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.crypto import constant_time_compare
from django.utils.http import base36_to_int
from django.utils.safestring import mark_safe
from django.contrib.auth.forms import AuthenticationForm as DjangoAuthenticationForm
from django.contrib.auth import authenticate
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.cache import cache
from django.apps import apps

config = apps.get_app_config("sic")

from sic.models import (
    Story,
    Hat,
    User,
    Tag,
    Taggregation,
    TaggregationHasTag,
    Message,
    StoryBookmark,
    CommentBookmark,
)
from sic.flatpages import DocumentationFlatPage, CommunityFlatPage, ExternalLinkFlatPage

CACHE_TIMEOUT = 60 * 60 * 12


class SicBackend(ModelBackend):
    def authenticate(
        self, request, username=None, password=None, username_as_alternative=False
    ):
        res = super().authenticate(request, username=username, password=password)
        if res is None and username_as_alternative is True:
            try:
                user = User.objects.get(username=username)
            except User.DoesNotExist:
                return None
            res = self.authenticate(request, username=user.email, password=password)
            return res
        return res

    def has_perm(self, user_obj, perm, obj):
        if user_obj.is_staff or user_obj.is_superuser or user_obj.is_moderator:
            return True
        karma = user_obj.karma
        is_banned = user_obj.is_banned
        is_active = user_obj.is_active
        if perm in ["sic.add_tag", "sic.change_tag"]:
            return karma >= config.MIN_KARMA_TO_EDIT_TAGS and not is_banned
        elif perm == "sic.delete_tag":
            return (
                (not obj.stories.exists()) if isinstance(obj, Tag) else True
            ) and not is_banned
        elif perm == "sic.add_story":
            return karma >= config.MIN_KARMA_TO_SUBMIT_STORIES and not is_banned
        elif perm in ["sic.change_story", "sic.delete_story"]:
            return obj.user == user_obj if isinstance(obj, Story) else True
        elif perm == "sic.add_hat":
            return (
                not user_obj.is_new_user and karma >= config.MIN_KARMA_TO_SUBMIT_STORIES
            )
        elif perm in ["sic.change_hat", "sic.delete_hat"]:
            return obj.user == user_obj if isinstance(obj, Hat) else True
        elif perm in ["sic.add_comment", "sic.add_story"]:
            return not is_banned
        elif perm == "sic.add_message":
            return not is_banned and is_active
        elif perm == "sic.add_invitation":
            return not is_banned and is_active
        elif perm == "sic.view_message" and isinstance(obj, Message):
            return user_obj in [obj.recipient, obj.author]
        elif perm == "sic.change_storybookmark" and isinstance(obj, StoryBookmark):
            return user_obj.id == obj.user_id
        elif perm == "sic.change_commentbookmark" and isinstance(obj, CommentBookmark):
            return user_obj.id == obj.user_id
        elif perm in ["change_taggregationhastag", "sic.delete_taggregationhastag"]:
            if is_banned:
                return False
            if isinstance(obj, TaggregationHasTag):
                return (
                    user_obj == obj.taggregation.creator
                    or user_obj in obj.taggregation.moderators.all()
                )
            return False
        else:
            return False


@receiver(post_save, sender=User)
def user_save_receiver(sender, instance, created, raw, using, update_fields, **kwargs):
    if not created:
        return
    defaults = Taggregation.objects.filter(default=True)
    instance.taggregation_subscriptions.set(defaults)
    instance.save()


def auth_context(request):
    footer_links = cache.get("footer_links", default=None)
    if footer_links is None:
        footer_links = ""
        for l in DocumentationFlatPage.objects.filter(show_in_footer=True).order_by(
            "order", "title"
        ):
            footer_links += f"""<li><a href="{l.flatpage_ptr.url}">{l.link_name if l.link_name else l.flatpage_ptr.title}</a></li>"""
        for l in CommunityFlatPage.objects.filter(show_in_footer=True).order_by(
            "order", "title"
        ):
            if l.show_inline:
                footer_links += l.flatpage_ptr.content
                continue
            footer_links += f"""<li><a href="{l.flatpage_ptr.url}">{l.link_name if l.link_name else l.flatpage_ptr.title}</a></li>"""
        for l in ExternalLinkFlatPage.objects.filter(show_in_footer=True).order_by(
            "order", "title"
        ):
            if l.show_inline:
                footer_links += l.flatpage_ptr.content
                continue
            footer_links += f"""<li><a href="{l.flatpage_ptr.url}" rel="external nofollow">{l.link_name if l.link_name else l.flatpage_ptr.title}</a></li>"""
        cache.set("footer_links", footer_links, timeout=CACHE_TIMEOUT)
    if request.user.is_authenticated:
        return {
            "show_avatars": request.user.show_avatars,
            "show_colors": request.user.show_colors,
            "show_stories_with_content_warning": request.user.show_stories_with_content_warning,
            "unread_messages": request.user.unread_messages,
            "font_size": request.session.get("font_size", None),
            "vivid_colors": request.session.get("vivid_colors", None),
            "footer_links": mark_safe(footer_links),
            "config": config,
        }
    return {
        "show_avatars": True,
        "show_stories_with_content_warning": False,
        "show_colors": True,
        "font_size": None,
        "vivid_colors": None,
        "footer_links": mark_safe(footer_links),
        "config": config,
    }


class AuthToken(PasswordResetTokenGenerator):
    def check_token(self, user, token):
        """
        Check that a password reset token is correct for a given user.
        """
        if not (user and token):
            return False
        # Parse the token
        try:
            ts_b36, _ = token.split("-")
        except ValueError:
            return False

        try:
            ts = base36_to_int(ts_b36)
        except ValueError:
            return False

        # Check that the timestamp/uid has not been tampered with
        if not constant_time_compare(self._make_token_with_timestamp(user, ts), token):
            return False
        return token == user.auth_token

    def _make_hash_value(self, user, timestamp):
        email_field = user.get_email_field_name()
        email = getattr(user, email_field, "") or ""
        return f"{user.pk}{user.password}{timestamp}{email}"


class AuthenticationForm(DjangoAuthenticationForm):
    def __init__(self, *args, **kwargs):
        super(AuthenticationForm, self).__init__(*args, **kwargs)
        self.fields["username"].label = "Email address or username"

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if username is not None and password:
            self.user_cache = authenticate(
                self.request,
                username=username,
                password=password,
                username_as_alternative=True,
            )
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data
