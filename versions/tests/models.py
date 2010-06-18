from django.db import models
from versions import VersionsModel

class Artist(VersionsModel):
    name = models.CharField(max_length=50)
