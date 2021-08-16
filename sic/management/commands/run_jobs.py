from multiprocessing import get_context
from django.core.management.base import BaseCommand
from sic.jobs import Job


class Command(BaseCommand):
    help = "Send digest mails"

    def handle(self, *args, **kwargs):
        for job in Job.objects.filter(active=True):
            job.run()
