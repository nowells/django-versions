from django.db import models

from versions.managers import VersionsManager, PublishedManager
from versions.repo import Versions

class VersionsModel(models.Model):
    versions_deleted = models.BooleanField(default=False)

    objects = VersionsManager()

    class Meta:
        abstract = True

    # Used to store the revision of the model.
    _versions_revision = None

    def save(self, *args, **kwargs):
        only_version = kwargs.pop('only_version', False)
        if not only_version:
            super(VersionsModel, self).save(*args, **kwargs)

        vc = Versions()
        return vc.stage(self)

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

