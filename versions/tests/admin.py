from django.contrib import admin
from versions.admin import VersionsAdmin
from versions.tests.models import Artist, Album

admin.site.register(Artist, VersionsAdmin)
admin.site.register(Album, VersionsAdmin)
