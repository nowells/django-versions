from django.db import connection
from django.db import models

from versions.base import revision
from versions.constants import VERSIONS_STATUS_PUBLISHED
from versions.query import VersionsQuerySet, VersionsQuery

class VersionsManager(models.Manager):
    use_for_related_fields = True

    def version(self, rev):
        return self.get_query_set(rev)

    def versions(self, instance_or_cls, pk=None):
        if pk is None:
            return [ x for x in revision.versions(instance_or_cls) ]
        else:
            return [ x for x in revision._versions(instance_or_cls, pk) ]

    def diff(self, instance, rev0, rev1=None):
        return revision.diff(instance, rev0, rev1)

    def get_query_set(self, rev=None, include_staged_delete=False, bypass_filter=False):
        if self.related_model_instance is not None:
            rev = rev and rev or self.related_model_instance._versions_revision

        query = VersionsQuery(self.model, connection, rev=rev, include_staged_delete=include_staged_delete)
        qs = VersionsQuerySet(model=self.model, query=query, rev=rev)

        # If we are looking up the current state of the model instances, filter out deleted models. The Versions system will take care of filtering out the deleted revised objects.
        if rev is None and not bypass_filter:
            qs = qs.filter(_versions_status=VERSIONS_STATUS_PUBLISHED)

        return qs

    def commit(self):
        for result in self.get_query_set(include_staged_delete=True):
            result.commit()

    def stage(self):
        for result in self.get_query_set():
            result.stage()
