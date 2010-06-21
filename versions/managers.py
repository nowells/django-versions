from django.db import connection
from django.db import models

from versions.repo import Versions
from versions.query import VersionsQuerySet, VersionsQuery

class VersionsManager(models.Manager):
    use_for_related_fields = True

    def version(self, revision):
        return self.get_query_set(revision)

    def revisions(self, instance):
        vc = Versions()
        return [ x.hex() for x in vc.revisions(instance) ]

    def diff(self, instance, rev0, rev1=None):
        vc = Versions()
        return vc.diff(instance, rev0, rev1)

    def get_query_set(self, revision=None):
        if self.reverse_model_instance is not None:
            revision = revision and revision or self.reverse_model_instance._versions_revision

        qs = VersionsQuerySet(model=self.model, query=VersionsQuery(self.model, connection, revision=revision), revision=revision)

        # If we are looking up the current state of the model instances, filter out deleted models. The Versions system will take care of filtering out the deleted revised objects.
        if revision is None:
            qs = qs.filter(versions_deleted=False)

        return qs

class PublishedManager(VersionsManager):
    pass
