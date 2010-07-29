from django.db import connection
from django.db.models import query
from django.db.models import sql
from django.db.models.fields import related
from django.db.models import signals
from django.utils import tree

from versions.base import revision
from versions.constants import VERSIONS_STATUS_DELETED, VERSIONS_STATUS_STAGED_DELETE
from versions.exceptions import VersionDoesNotExist, VersionsException
from versions.fields import VersionsReverseSingleRelatedObjectDescriptor, VersionsForeignRelatedObjectsDescriptor, VersionsReverseManyRelatedObjectsDescriptor

# Registry of table names to Versioned models
_versions_table_mappings = {}

def stage_related_models(sender, instance, created, **kwargs):
    """
    This signal handler is used to alert objects to changes in the ForeignKey of related objects.
    We capture both the creation of a new ForeignKey relationship, as well as the removal or changing
    of an existing ForeignKey relationship.
    """
    for field, models in instance._versions_related_updates.items():
        related_field = instance._meta.get_field(field).related.get_accessor_name()
        old_related_model, new_related_model = models
        if old_related_model is not None:
            revision.stage(old_related_model, related_updates={'removed': {related_field: [instance]}})
        revision.stage(new_related_model, related_updates={'added': {related_field: [instance]}})

def setup_versioned_models(sender, **kargs):
    from versions.models import VersionsModel
    if issubclass(sender, VersionsModel):
        # Register this model with the version registry.
        qn = connection.ops.quote_name
        _versions_table_mappings[qn(sender._meta.db_table)] = sender

        try:
            name_map = sender._meta._name_map
        except AttributeError:
            name_map = sender._meta.init_name_map()

        for name, data in name_map.items():
            field = data[0]
            if isinstance(field, related.ForeignKey):
                setattr(sender, name, VersionsReverseSingleRelatedObjectDescriptor(field))
                setattr(field.rel.to, field.related.get_accessor_name(), VersionsForeignRelatedObjectsDescriptor(field.related))
                signals.post_save.connect(stage_related_models, sender=field.rel.to, dispatch_uid='versions_foreignkey_related_object_update')
            elif isinstance(field, related.ManyToManyField):
                setattr(sender, name, VersionsReverseManyRelatedObjectsDescriptor(field))

        # Clean up after ourselves so that no previously initialized field caches are invalid.
        for cache_name in ('_related_many_to_many_cache', '_name_name', '_related_objects_cache', '_m2m_cache', '_field_cache',):
            try:
                delattr(sender._meta, cache_name)
            except:
                pass

signals.class_prepared.connect(setup_versioned_models)

def _remove_versions_status_filter(node):
    for i, child in enumerate(node.children):
        if isinstance(child, tree.Node):
            _remove_versions_status_filter(child)
        else:
            if child[0][1] == '_versions_status':
                del node.children[i]

class VersionsQuery(sql.Query):
    def __init__(self, *args, **kwargs):
        self._revision = kwargs.pop('rev', None)
        self._include_staged_delete = kwargs.pop('include_staged_delete', False)
        super(VersionsQuery, self).__init__(*args, **kwargs)

    def clone(self, *args, **kwargs):
        obj = super(VersionsQuery, self).clone(*args, **kwargs)
        obj._revision = self._revision
        obj._include_staged_delete = self._include_staged_delete
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
                        rev_data = revision._version(field['model'], row[field['pk']], rev=self._revision)
                        field_data = rev_data.get('field', {})
                        related_data = rev_data.get('related', {})

                        # Exclude objects that were deleted in the past.
                        if field_data.get('_versions_status', None) == VERSIONS_STATUS_DELETED:
                            exists = False
                            break
                        elif field_data.get('_versions_status', None) == VERSIONS_STATUS_STAGED_DELETE and not self._include_staged_delete:
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
        self._revision = kwargs.pop('rev', None)
        super(VersionsQuerySet, self).__init__(*args, **kwargs)

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

    def delete(self, *args, **kwargs):
        for result in self.iterator():
            result.delete()

    def values(self, *args, **kwargs):
        # TODO: This is a HACK to to allow us to capture when a model object is going to be saved, however, that object would be excluded
        # due to the fact that is it not currently PUBLISHED in the database. The ModelBase.save_base function does a check for existance
        # of an object to determine whether to update or insert, so we need to remove the automatic filter applied by the VersionsManager
        # to allow the save_base function to see an object, even if the database has that object as being some _versions_status other than
        # PUBLISHED.
        if args == ('a',):
            _remove_versions_status_filter(self.query.where)
        return super(VersionsQuerySet, self).values(*args, **kwargs)

    def _update(self, *args, **kwargs):
        # We need to filter out the versions_status filter for the update, so that when save_base function calls
        # `manager.filter(pk=pk_val)._update(values)` the manager returns the proper data to be updated.
        _remove_versions_status_filter(self.query.where)
        return super(VersionsQuerySet, self)._update(*args, **kwargs)
