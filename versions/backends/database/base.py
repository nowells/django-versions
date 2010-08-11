import logging
import os

from versions.backends.base import BaseRepository
from versions.base import revision, Version
from versions.exceptions import VersionDoesNotExist
from versions.backends.database.models import Changeset, Revision

class Repository(BaseRepository):
    def commit(self, changes):
        changeset = Changeset()
        changeset.message = revision.message
        changeset.user = revision.user.id
        changeset.save()

        for path, data in changes.items():
            rev = Revision()
            rev.changeset = changeset
            rev.path = path
            rev.data = data
            rev.save()

        return changeset.pk

    def versions(self, path):
        return Changeset.objects.filter(revisions__path=path).order_by('-pk')

    def version(self, item, rev=None):
        revision = Revision.objects.filter(path=item)
        if rev is not None and rev != 'tip':
            revision = revision.filter(changeset__pk__lte=rev)
        revision = revision.order_by('-changeset__pk')[:1]
        try:
            version = revision.get()
        except Revision.DoesNotExist:
            raise VersionDoesNotExist('Version `%s` does not exist for %s' % (rev, item))

        return str(version.data)
