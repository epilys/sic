from django.contrib.flatpages.models import FlatPage
from django.db import models


class DocumentationFlatPage(FlatPage):
    link_name = models.TextField(null=True)
    order = models.PositiveIntegerField(null=True, blank=True, default=None)
    show_in_footer = models.BooleanField(null=False, blank=True, default=False)
    show_in_header = models.BooleanField(null=False, blank=True, default=False)
    show_in_about = models.BooleanField(
        "Show in about page", null=False, blank=True, default=True
    )


class CommunityFlatPage(FlatPage):
    link_name = models.TextField(null=True)
    order = models.PositiveIntegerField(null=True, blank=True, default=None)
    show_inline = models.BooleanField(null=False, blank=True, default=False)
    show_in_footer = models.BooleanField(null=False, blank=True, default=False)
    show_in_header = models.BooleanField(null=False, blank=True, default=False)
    show_in_about = models.BooleanField(
        "Show in about page", null=False, blank=True, default=True
    )


class ExternalLinkFlatPage(FlatPage):
    link_name = models.TextField(null=False, blank=False)
    external_url = models.URLField(null=False, blank=False)
    order = models.PositiveIntegerField(null=True, blank=True, default=None)
    show_inline = models.BooleanField(null=False, blank=True, default=False)
    show_in_footer = models.BooleanField(null=False, blank=True, default=False)
    show_in_header = models.BooleanField(null=False, blank=True, default=False)
    show_in_about = models.BooleanField(
        "Show in about page", null=False, blank=True, default=True
    )
