from django.db import models

from versions.constants import VERSIONS_STATUS_CHOICES, VERSIONS_STATUS_PUBLISHED, VERSIONS_STATUS_DELETED, VERSIONS_STATUS_UNPUBLISHED
from versions.exceptions import VersionsException
from versions.fields import VersionsManyToManyField
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
    _versions_unpublished_changes = None
    _versions_related_updates = None

    def __init__(self, *args, **kwargs):
        self._versions_revision = None
        self._versions_related_updates = {}
        self._versions_unpublished_changes = {}
        super(VersionsModel, self).__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        should_save = kwargs.pop('save', self.versions_status == VERSIONS_STATUS_PUBLISHED)
        should_stage = kwargs.pop('stage', True)

        # We save the model only if it is a new instance, or if we have been told to save (i.e. one of the helper functions.)
        if self.pk is None or should_save:
            super(VersionsModel, self).save(*args, **kwargs)

        if should_stage:
            return versions.stage(self)

    def delete(self, *args, **kwargs):
        self.versions_status = VERSIONS_STATUS_DELETED
        return self.save(save=True)

    def publish(self):
        self.versions_status = VERSIONS_STATUS_PUBLISHED
        self.save(stage=False)

        if self._versions_revision is None:
            data = versions.data(self)
        else:
            data = versions.version(self, rev=self._versions_revision)

        for name, ids in data['related'].items():
            try:
                field = self._meta.get_field_by_name(name)[0]
            except:
                pass
            else:
                if isinstance(field, VersionsManyToManyField):
                    setattr(self, name, self._versions_unpublished_changes.get(name, ids))

        return versions.stage(self)

    def unpublish(self):
        self.versions_status = VERSIONS_STATUS_UNPUBLISHED
        return self.save()
