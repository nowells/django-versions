from django.db import models

from versions.exceptions import VersionsException
from versions.managers import VersionsManager, PublishedManager
from versions.repo import versions

class VersionsOptions(object):
    @classmethod
    def contribute_to_class(klass, cls, name):
        include = getattr(klass, 'include', [])
        exclude = getattr(klass, 'exclude', [])

        invalid_excludes = set(['versions_deleted', 'versions_published']).intersection(exclude)
        if invalid_excludes:
            raise VersionsException('You cannot include `%s` in a VersionOptions exclude.' % ', '.join(invalid_excludes))

        cls._versions_options = VersionsOptions()
        cls._versions_options.include = include
        cls._versions_options.exclude = exclude
        cls._versions_options.core_include = ['versions_deleted', 'versions_published']

class VersionsModel(models.Model):
    versions_deleted = models.BooleanField(default=False)

    objects = VersionsManager()

    class Meta:
        abstract = True

    class Versions(VersionsOptions):
        exclude = []
        include = []

    # Used to store the revision of the model.
    _versions_revision = None

    def save(self, *args, **kwargs):
        only_version = kwargs.pop('only_version', False)

        # We save the model only if it is a new instance, or if we have not been told to bypass saving.
        if self.pk is None or not only_version:
            super(VersionsModel, self).save(*args, **kwargs)

        return versions.stage(self)

    def delete(self, *args, **kwargs):
        self.versions_deleted = True
        self.save()

class PublishedModel(VersionsModel):
    versions_published = models.BooleanField(default=False)

    objects = PublishedManager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        kwargs['only_version'] = not self.versions_published
        return super(PublishedModel, self).save(*args, **kwargs)

