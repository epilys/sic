from django.db import connections
from django.db.models.signals import post_save
from django.db.models.expressions import RawSQL
from django.dispatch import receiver
from django.core.mail import EmailMessage
from django.apps import apps

config = apps.get_app_config("sic")
from .models import Comment, Story, User, Message, Notification, InvitationRequest


@receiver(post_save, sender=Comment)
def comment_save_receiver(
    sender, instance, created, raw, using, update_fields, **kwargs
):
    comment = instance
    if (
        created
        and (
            (comment.parent and comment.parent.user != comment.user)
            or (comment.parent is None and comment.story.user != comment.user)
        )
        and not comment.deleted
    ):
        target = "comment" if comment.parent else "story"
        plain_text_comment = comment.text_to_plain_text
        Notification.objects.create(
            user=comment.parent.user if comment.parent else comment.story.user,
            name=f"New reply in {comment.story.title}",
            kind=Notification.Kind.REPLY,
            body=f"{comment.user} has replied to your {target}:\n\n{plain_text_comment}",
            caused_by=comment.user,
            url=comment.get_absolute_url(),
        )
    if config.DETECT_USERNAME_MENTIONS_IN_COMMENTS:
        with connections["default"].cursor() as cursor:
            mentioned_users = User.objects.filter(
                id__in=RawSQL(
                    f"SELECT user.id AS id FROM {config.MENTION_TOKENIZER_NAME}, sic_user AS user, sic_comment AS comment WHERE input = comment.text AND comment.id = %s AND token = user.username",
                    (instance.pk,),
                ),
            ).exclude(id=comment.user.pk)
            if comment.parent:
                mentioned_users = mentioned_users.exclude(id=comment.parent.user.pk)
            else:
                mentioned_users = mentioned_users.exclude(id=comment.story.user.pk)
            if mentioned_users.exists():
                plain_text_comment = comment.text_to_plain_text
                for user in mentioned_users:
                    Notification.objects.create(
                        user=user,
                        name=f"{comment.user} has mentioned you in {comment.story.title}",
                        kind=Notification.Kind.MENTION,
                        body=f"{comment.user} has mentioned you:\n\n{plain_text_comment}",
                        caused_by=comment.user,
                        url=comment.get_absolute_url(),
                    )


@receiver(post_save, sender=Message)
def message_sent_receiver(
    sender, instance, created, raw, using, update_fields, **kwargs
):
    if created:
        message = instance
        Notification.objects.create(
            user=message.recipient,
            name=f"{message.author} sent you a message: {message.subject}",
            kind=Notification.Kind.MESSAGE,
            body=message.body if message.body else "",
            caused_by=message.author,
            url=message.get_absolute_url(),
        )


@receiver(post_save, sender=Notification)
def notification_created_receiver(
    sender, instance, created, raw, using, update_fields, **kwargs
):
    if created:
        if instance.kind in {Notification.Kind.MENTION}:
            if not instance.user.email_mentions:
                return
        elif instance.kind in {Notification.Kind.MESSAGE}:
            if not instance.user.email_messages:
                return
        elif instance.kind in {Notification.Kind.REPLY}:
            if not instance.user.email_replies:
                return
        elif not instance.user.email_notifications:
            return
        instance.send()


@receiver(post_save, sender=InvitationRequest)
def new_invitation_request_receiver(
    sender, instance, created, raw, using, update_fields, **kwargs
):
    req = instance
    if created:
        EmailMessage(
            f"[sic] confirmation of your invitation request",
            f"This message is just a confirmation we have received your request.",
            config.NOTIFICATION_FROM,
            [req.address],
            headers={"Message-ID": config.make_msgid()},
        ).send(fail_silently=False)
