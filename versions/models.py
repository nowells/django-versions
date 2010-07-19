from django.db import models

from versions.constants import VERSIONS_STATUS_CHOICES, VERSIONS_STATUS_PUBLISHED, VERSIONS_STATUS_DELETED, VERSIONS_STATUS_STAGED_EDITS, VERSIONS_STATUS_STAGED_DELETE
from versions.exceptions import VersionsException
from versions.fields import VersionsManyToManyField
from versions.managers import VersionsManager
from versions.repo import versions

class VersionsOptions(object):
    @classmethod
    def contribute_to_class(klass, cls, name):
        include = getattr(klass, 'include', [])
        exclude = getattr(klass, 'exclude', [])

        invalid_excludes = set(['_versions_status']).intersection(exclude)
        if invalid_excludes:
            raise VersionsException('You cannot include `%s` in a VersionOptions exclude.' % ', '.join(invalid_excludes))

        cls._versions_options = VersionsOptions()
        cls._versions_options.include = include
        cls._versions_options.exclude = exclude
        cls._versions_options.core_include = ['_versions_status']

class VersionsModel(models.Model):
    _versions_status = models.PositiveIntegerField(choices=VERSIONS_STATUS_CHOICES, default=VERSIONS_STATUS_PUBLISHED)
    def versions_status(self):
        return self._versions_status
    versions_status = property(versions_status)

    objects = VersionsManager()

    class Meta:
        abstract = True

    class Versions(VersionsOptions):
        exclude = []
        include = []

    # Used to store the revision of the model.
    _versions_revision = None
    _versions_staged_changes = None
    _versions_related_updates = None

    def __init__(self, *args, **kwargs):
        self._versions_revision = None
        self._versions_related_updates = {}
        self._versions_staged_changes = {}
        super(VersionsModel, self).__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        if (self._get_pk_val() is None or self._versions_status in (VERSIONS_STATUS_PUBLISHED, VERSIONS_STATUS_DELETED)):
            super(VersionsModel, self).save(*args, **kwargs)
        return versions.stage(self)

    def delete(self, *args, **kwargs):
        if self._versions_status in (VERSIONS_STATUS_STAGED_EDITS, VERSIONS_STATUS_STAGED_DELETE,):
            self._versions_status = VERSIONS_STATUS_STAGED_DELETE
        else:
            self._versions_status = VERSIONS_STATUS_DELETED
        return self.save()

    def commit(self):
        if self._versions_status == VERSIONS_STATUS_STAGED_DELETE:
            self._versions_status = VERSIONS_STATUS_DELETED
        else:
            self._versions_status = VERSIONS_STATUS_PUBLISHED

        # We don't want to call our save method, because we want to stage the state of this model until we set the state of all unpublihsed manytomany edits.
        super(VersionsModel, self).save()

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
                    setattr(self, name, self._versions_staged_changes.get(name, ids))

        return versions.stage(self)

    def stage(self):
        self._versions_status = VERSIONS_STATUS_STAGED_EDITS
        return self.save()
