try:
    from functools import wraps
except ImportError:
    from django.utils.functional import wraps  # Python 2.3, 2.4 fallback.

from django.db import connection
from django.db import models
from django.db.models import base
from django.db.models import query
from django.db.models import sql
from django.db.models.fields import related

from versions.exceptions import VersionDoesNotExist, VersionsException
from versions.repo import Versions

# Registry of table names to Versioned models
_versions_table_mappings = {}

class VersionsQuery(sql.Query):
    def __init__(self, *args, **kwargs):
        self._revision = kwargs.pop('revision', None)
        super(VersionsQuery, self).__init__(*args, **kwargs)

    def clone(self, *args, **kwargs):
        obj = super(VersionsQuery, self).clone(*args, **kwargs)
        obj._revision = self._revision
        return obj

    def get_field_mapping(self):
        qn = connection.ops.quote_name

        extra_names = self.extra_select.keys()
        field_names = self.get_columns()
        field_start = len(extra_names)

        fields = {}
        for offset, field in enumerate(field_names):
            table, column = field.split('.')
            if table in _versions_table_mappings:
                model = _versions_table_mappings[table]

                if table not in fields:
                    expected_pk_column = '%s.%s' % (qn(model._meta.db_table), qn(model._meta.pk.attname))
                    # This is a sanity check to ensure that we are mapping the right database table to the right model.
                    # In order for the revisions code to work, we always need to have the pk of a record returned.
                    if field != expected_pk_column:
                        raise Exception('Error while locating primary_key column, expected to find %s, but found %s instead' % (expected_pk_column, column))

                    fields[table] = {
                        'model': _versions_table_mappings[table],
                        'pk': field_start + offset,
                        'columns': dict([ (qn(x.get_attname_column()[1]), {'field': x.get_attname_column()[0], 'position': None}) for x in model._meta.fields ]),
                        }
                fields[table]['columns'][column]['position'] = field_start + offset
        return fields

    def results_iter(self):
        if self._revision is None:
            for row in super(VersionsQuery, self).results_iter():
                yield row
        else:
            fields = None
            vc = Versions()

            for row in super(VersionsQuery, self).results_iter():
                row = list(row)
                if fields is None:
                    fields = self.get_field_mapping()

                # Track whether this row existed at the time of the revision.
                exists = True
                for field in fields.values():
                    try:
                        # TODO: exclude models that existed, but were deleted at this revision?
                        # TODO: how do we handle select_related queries?
                        #    1) if the primary object does not exist at this revision, it should be skipped.
                        #    2) what about objects included in select_reated? (if the filter was only filtering on the primary object,
                        #       we should be able to set data from the select_related model that does not exist at this revision to None,
                        #       however, what do we do if the query filtered on the related object?
                        #    3) What if this object is only being included because the database value of the selected object at an old revision matched,
                        #       but the existing revision of that object does not?
                        rev_data = vc._version(field['model'], row[field['pk']], rev=self._revision)

                        # Exclude objects that were deleted in the past.
                        if rev_data.get('versions_deleted', False):
                            exists = False
                            break
                        else:
                            for column in field['columns'].values():
                                if column['position'] is not None:
                                    row[column['position']] = rev_data.get(column['field'], row[column['position']])
                    except VersionDoesNotExist:
                        exists = False
                        break

                # If all of the objects within this row existed at the specified revision, yeild the row.
                if exists:
                    yield row

class VersionsQuerySet(query.QuerySet):
    def __init__(self, *args, **kwargs):
        self._revision = kwargs.pop('revision', None)
        super(VersionsQuerySet, self).__init__(*args, **kwargs)

        # Register this model with the version registry.
        qn = connection.ops.quote_name
        _versions_table_mappings[qn(self.model._meta.db_table)] = self.model

    def _clone(self, *args, **kwargs):
        obj = super(VersionsQuerySet, self)._clone(*args, **kwargs)
        obj._revision = self._revision
        return obj

    def iterator(self):
        for result in super(VersionsQuerySet, self).iterator():
            result._versions_revision = self._revision
            yield result

    def count(self, *args, **kwargs):
        if self._revision is not None:
            raise VersionsException('You cannot use run a `%s` operation on a queryset that is finding versioned objects.' % 'count')
        return super(VersionsQuerySet, self).count(*args, **kwargs)

    def values_list(self, *args, **kwargs):
        if self._revision is not None:
            raise VersionsException('You cannot use run a `%s` operation on a queryset that is finding versioned objects.' % 'values_list')
        return super(VersionsQuerySet, self).values_list(*args, **kwargs)

    def aggregate(self, *args, **kwargs):
        if self._revision is not None:
            raise VersionsException('You cannot use run a `%s` operation on a queryset that is finding versioned objects.' % 'aggregate')
        return super(VersionsQuerySet, self).aggregate(*args, **kwargs)

    def annotate(self, *args, **kwargs):
        if self._revision is not None:
            raise VersionsException('You cannot use run a `%s` operation on a queryset that is finding versioned objects.' % 'annotate')
        return super(VersionsQuerySet, self).annotate(*args, **kwargs)

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

class VersionsModel(models.Model):
    # Attributes
    _versions_revision = None

    # Fields
    versions_deleted = models.BooleanField(default=False)

    objects = VersionsManager()

    class Meta:
        abstract = True

    def __init__(self, *args, **kwargs):
        super(VersionsModel, self).__init__(*args, **kwargs)

    def save(self, *args, **kwargs):
        super(VersionsModel, self).save(*args, **kwargs)
        vc = Versions()
        return vc.stage(self)

    def delete(self, *args, **kwargs):
        self.versions_deleted = True
        self.save()
