from django.db import connection
from django.db import models
from django.db.models import base
from django.db.models import query
from django.db.models import sql
from django.db.models.fields import related

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

                for field in fields.values():
                    try:
                        rev_data = vc._version(field['model'], row[field['pk']], rev=self._revision)
                        for column in field['columns'].values():
                            if column['position'] is not None:
                                row[column['position']] = rev_data.get(column['field'], row[column['position']])
                    except LookupError:
                        # TODO: how should we handle this?
                        pass
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
        return qs

class VersionsModel(models.Model):
    # Attributes
    _versions_revision = None

    # Fields
    #versions_deleted = models.BooleanField(default=False)

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
