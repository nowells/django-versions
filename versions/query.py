from django.db import connection
from django.db.models import query
from django.db.models import sql

from versions.constants import VERSIONS_STATUS_DELETED, VERSIONS_STATUS_STAGED_DELETE
from versions.exceptions import VersionDoesNotExist, VersionsException
from versions.repo import versions

# Registry of table names to Versioned models
_versions_table_mappings = {}

class VersionsQuery(sql.Query):
    def __init__(self, *args, **kwargs):
        self._revision = kwargs.pop('revision', None)
        self._include_staged_delete = kwargs.pop('include_staged_delete', False)
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
            try:
                table, column = field.split('.')
            except ValueError:
                continue
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

            for row in super(VersionsQuery, self).results_iter():
                row = list(row)
                if fields is None:
                    fields = self.get_field_mapping()

                # Track whether this row existed at the time of the revision.
                exists = True
                for field in fields.values():
                    try:
                        # TODO: how do we handle select_related queries?
                        #    1) if the primary object does not exist at this revision, it should be skipped.
                        #    2) what about objects included in select_reated? (if the filter was only filtering on the primary object,
                        #       we should be able to set data from the select_related model that does not exist at this revision to None,
                        #       however, what do we do if the query filtered on the related object?
                        #    3) What if this object is only being included because the database value of the selected object at an old revision matched,
                        #       but the existing revision of that object does not?
                        rev_data = versions._version(field['model'], row[field['pk']], rev=self._revision)
                        field_data = rev_data.get('field', {})
                        related_data = rev_data.get('related', {})

                        # Exclude objects that were deleted in the past.
                        if field_data.get('versions_status', None) == VERSIONS_STATUS_DELETED:
                            exists = False
                            break
                        elif field_data.get('versions_status', None) == VERSIONS_STATUS_STAGED_DELETE and not self._include_staged_delete:
                            exists = False
                            break
                        else:
                            for column in field['columns'].values():
                                if column['position'] is not None:
                                    row[column['position']] = field_data.get(column['field'], row[column['position']])
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
            raise VersionsException('You cannot call `%s` on a queryset that is finding versioned objects.' % 'count')
        return super(VersionsQuerySet, self).count(*args, **kwargs)

    def values_list(self, *args, **kwargs):
        if self._revision is not None:
            raise VersionsException('You cannot call `%s` on a queryset that is finding versioned objects.' % 'values_list')
        return super(VersionsQuerySet, self).values_list(*args, **kwargs)

    def aggregate(self, *args, **kwargs):
        if self._revision is not None:
            raise VersionsException('You cannot call `%s` on a queryset that is finding versioned objects.' % 'aggregate')
        return super(VersionsQuerySet, self).aggregate(*args, **kwargs)

    def annotate(self, *args, **kwargs):
        if self._revision is not None:
            raise VersionsException('You cannot call `%s` on a queryset that is finding versioned objects.' % 'annotate')
        return super(VersionsQuerySet, self).annotate(*args, **kwargs)
