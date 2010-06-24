from django.contrib.auth.models import User
from django.db import models
from versions.fields import VersionsManyToManyField, VersionsForeignKey
from versions.models import VersionsModel, PublishedModel, VersionsOptions

class Artist(VersionsModel):
    name = models.CharField(max_length=50)
    fans = VersionsManyToManyField(User, blank=True, related_name='favorite_artists')
    time_modified = models.DateTimeField(auto_now=True)

    class Versions(VersionsOptions):
        exclude = ['time_modified']

    def __unicode__(self):
        return self.name

class Album(VersionsModel):
    artist = VersionsForeignKey(Artist, related_name='albums')
    title = models.CharField(max_length=50)
    time_modified = models.DateTimeField(auto_now=True)

    class Versions(VersionsOptions):
        include = ['title']

    def __unicode__(self):
        return self.title

class Song(VersionsModel):
    album = VersionsForeignKey(Album, related_name='songs')
    title = models.CharField(max_length=50)
    seconds = models.PositiveIntegerField(null=True, blank=True)

    def __unicode__(self):
        return self.title

class Lyrics(PublishedModel):
    song = VersionsForeignKey(Song, related_name='lyrics')
    text = models.TextField(blank=True)

    def __unicode__(self):
        return self.text
