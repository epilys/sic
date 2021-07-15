from django.contrib.auth.backends import ModelBackend
from .apps import SicAppConfig as config
from .models import Story, Hat


class SicBackend(ModelBackend):
    def has_perm(self, user_obj, perm, obj):
        if user_obj.is_staff or user_obj.is_superuser:
            return True
        karma = user_obj.karma()
        if perm in ["sic.add_tag", "sic.change_tag", "sic.delete_tag"]:
            return (
                not user_obj.is_new_user()
                and karma >= config.MIN_KARMA_TO_SUBMIT_STORIES
            )
        elif perm == "sic.add_story":
            return karma >= config.MIN_KARMA_TO_SUBMIT_STORIES
        elif (
            perm in ["sic.change_story", "sic.delete_story"]
            and isinstance(obj, Story)
            and obj.user == user_obj
        ):
            return True
        elif perm == "sic.add_hat":
            return (
                not user_obj.is_new_user()
                and karma >= config.MIN_KARMA_TO_SUBMIT_STORIES
            )
        elif (
            perm in ["sic.change_hat", "sic.delete_hat"]
            and isinstance(obj, Hat)
            and obj.user == user_obj
        ):
            return True
        else:
            return False


def auth_context(request):
    if request.user.is_authenticated:
        return {
            "show_avatars": request.user.show_avatars,
            "show_story_previews": request.user.show_story_previews,
            "show_submitted_story_threads": request.user.show_submitted_story_threads,
            "show_colors": request.user.show_colors,
            "unread_messages": request.user.received_messages.filter(
                read_by_recipient=False
            ).count(),
        }
    return {
        "show_avatars": True,
        "show_story_previews": False,
        "show_submitted_story_threads": False,
        "show_colors": True,
    }
