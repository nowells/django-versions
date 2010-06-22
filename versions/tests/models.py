from django.contrib.auth.models import User
from django.db import models
from versions.fields import VersionsManyToManyField, VersionsForeignKey
from versions.models import VersionsModel, PublishedModel

class Artist(VersionsModel):
    name = models.CharField(max_length=50)
    fans = VersionsManyToManyField(User, blank=True, related_name='favorite_artists')

    def __unicode__(self):
        return self.name

class Albumn(VersionsModel):
    artist = VersionsForeignKey(Artist, related_name='albumns')
    title = models.CharField(max_length=50)

    def __unicode__(self):
        return self.title

class Song(VersionsModel):
    albumn = VersionsForeignKey(Albumn, related_name='songs')
    title = models.CharField(max_length=50)
    seconds = models.PositiveIntegerField(null=True, blank=True)

    def __unicode__(self):
        return self.title

class Lyrics(PublishedModel):
    song = VersionsForeignKey(Song, related_name='lyrics')
    text = models.TextField(blank=True)

    def __unicode__(self):
        return self.text
