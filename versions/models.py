from django.db import models

from versions.constants import VERSIONS_STATUS_CHOICES, VERSIONS_STATUS_PUBLISHED, VERSIONS_STATUS_DELETED, VERSIONS_STATUS_UNPUBLISHED
from versions.exceptions import VersionsException
from versions.managers import VersionsManager
from versions.repo import versions

class VersionsOptions(object):
    @classmethod
    def contribute_to_class(klass, cls, name):
        include = getattr(klass, 'include', [])
        exclude = getattr(klass, 'exclude', [])

        invalid_excludes = set(['versions_status']).intersection(exclude)
        if invalid_excludes:
            raise VersionsException('You cannot include `%s` in a VersionOptions exclude.' % ', '.join(invalid_excludes))

        cls._versions_options = VersionsOptions()
        cls._versions_options.include = include
        cls._versions_options.exclude = exclude
        cls._versions_options.core_include = ['versions_status']

class VersionsModel(models.Model):
    versions_status = models.PositiveIntegerField(choices=VERSIONS_STATUS_CHOICES, default=VERSIONS_STATUS_PUBLISHED)

    objects = VersionsManager()

    class Meta:
        abstract = True

    class Versions(VersionsOptions):
        exclude = []
        include = []

    # Used to store the revision of the model.
    _versions_revision = None
    _versions_unpublished_changes = {}

    def save(self, *args, **kwargs):
        publish = self.versions_status == VERSIONS_STATUS_PUBLISHED
        self.versions_status = kwargs.pop('versions_status', self.versions_status)

        # We save the model only if it is a new instance, or if we are not publishing the object.
        if self.pk is None or publish:
            super(VersionsModel, self).save(*args, **kwargs)

        return versions.stage(self)

    def delete(self, *args, **kwargs):
        return self.save(versions_status=VERSIONS_STATUS_DELETED)

    def publish(self):
        self.versions_status = VERSIONS_STATUS_PUBLISHED
        return self.save()

    def unpublish(self):
        return self.save(versions_status=VERSIONS_STATUS_UNPUBLISHED)
