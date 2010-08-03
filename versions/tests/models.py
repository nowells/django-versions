from django.db import models
from versions.models import VersionsModel, VersionsOptions

class Venue(VersionsModel):
    name = models.CharField(max_length=50)
    artists = models.ManyToManyField('tests.Artist', blank=True, related_name='venues')
    recent_artists = models.ManyToManyField('tests.Artist', blank=True, related_name='recent_venues')

class Artist(VersionsModel):
    name = models.CharField(max_length=50)
    fans = models.ManyToManyField('auth.User', blank=True, related_name='favorite_artists')
    time_modified = models.DateTimeField(auto_now=True)

    class Versions(VersionsOptions):
        exclude = ['time_modified']

    def __unicode__(self):
        return self.name

class Album(VersionsModel):
    artist = models.ForeignKey(Artist, related_name='albums')
    title = models.CharField(max_length=50)
    time_modified = models.DateTimeField(auto_now=True)

    class Versions(VersionsOptions):
        include = ['title']

    def __unicode__(self):
        return self.title

class Song(VersionsModel):
    album = models.ForeignKey(Album, related_name='songs')
    title = models.CharField(max_length=50)
    seconds = models.PositiveIntegerField(null=True, blank=True)

    def __unicode__(self):
        return self.title

class Lyrics(VersionsModel):
    song = models.ForeignKey(Song, related_name='lyrics')
    text = models.TextField(blank=True)

    def __unicode__(self):
        return self.text
