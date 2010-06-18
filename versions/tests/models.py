from django.db import models
from versions import VersionsModel

class Artist(VersionsModel):
    name = models.CharField(max_length=50)

class Albumn(VersionsModel):
    artist = models.ForeignKey(Artist, related_name='albumns')
    title = models.CharField(max_length=50)

class Song(VersionsModel):
    albumn = models.ForeignKey(Albumn, related_name='songs')
    title = models.CharField(max_length=50)
    seconds = models.PositiveIntegerField(null=True, blank=True)
