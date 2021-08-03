from django.core.management.base import BaseCommand
from sic.mail import Digest
from sic.apps import SicAppConfig as config


class Command(BaseCommand):
    help = "Send digest mails"

    def handle(self, *args, **kwargs):
        Digest.send_digests()
