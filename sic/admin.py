from django.contrib import admin
from .models import *

admin.site.register(User)
admin.site.register(Story)
admin.site.register(Comment)
admin.site.register(Hat)
admin.site.register(Message)
admin.site.register(Tag)
