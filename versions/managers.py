from django.db import connection
from django.db import models

from versions.constants import VERSIONS_STATUS_PUBLISHED
from versions.repo import versions
from versions.query import VersionsQuerySet, VersionsQuery

class VersionsManager(models.Manager):
    use_for_related_fields = True

    def version(self, revision):
        return self.__versions_get_query_set(revision)

    def revisions(self, instance):
        return [ x.hex() for x in versions.revisions(instance) ]

    def diff(self, instance, rev0, rev1=None):
        return versions.diff(instance, rev0, rev1)

    def get_query_set(self):
        return self.__versions_get_query_set()

    def __versions_get_query_set(self, revision=None, include_staged_delete=False):
        if self.related_model_instance is not None:
            revision = revision and revision or self.related_model_instance._versions_revision

        query = VersionsQuery(self.model, connection, revision=revision, include_staged_delete=include_staged_delete)
        qs = VersionsQuerySet(model=self.model, query=query, revision=revision)

        # If we are looking up the current state of the model instances, filter out deleted models. The Versions system will take care of filtering out the deleted revised objects.
        if revision is None:
            qs = qs.filter(versions_status=VERSIONS_STATUS_PUBLISHED)

        return qs

    def commit(self):
        for result in self.__versions_get_query_set(include_staged_delete=True):
            result.commit()

    def stage(self):
        for result in self.__versions_get_query_set():
            result.stage()
