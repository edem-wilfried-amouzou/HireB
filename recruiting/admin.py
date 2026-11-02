from django.contrib import admin

from . import models

admin.site.register(models.Recruitment)
admin.site.register(models.Application)
admin.site.register(models.Member)
admin.site.register(models.Invitation)
admin.site.register(models.Notification)
