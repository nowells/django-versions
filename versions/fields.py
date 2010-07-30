from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
from django.db.models.fields import related

from versions.base import revision
from versions.constants import VERSIONS_STATUS_STAGED_EDITS, VERSIONS_STATUS_PUBLISHED

class VersionsReverseSingleRelatedObjectDescriptor(related.ReverseSingleRelatedObjectDescriptor):
    def __set__(self, instance, value):
        try:
            old_value = getattr(instance, self.field.name, None)
        except ObjectDoesNotExist:
            old_value = None

        result = super(VersionsReverseSingleRelatedObjectDescriptor, self).__set__(instance, value)
        if old_value != value:
            revision.stage_related_update(instance, self.field.name, old_value, value)
        return result

class VersionsForeignRelatedObjectsDescriptor(related.ForeignRelatedObjectsDescriptor):
    def __get__(self, instance, instance_type=None):
        if instance is None:
            return self

        manager = super(VersionsForeignRelatedObjectsDescriptor, self).__get__(instance, instance_type)
        class VersionsRelatedManager(manager.__class__):
            def get_unfiltered_query_set(self):
                return super(VersionsRelatedManager, self).get_query_set()

            def get_query_set(self, *args, **kwargs):
                rev = kwargs.get('rev', None)
                if self.related_model_instance is not None and hasattr(self.related_model_instance, '_versions_revision'):
                    rev = self.related_model_instance._versions_revision

                if rev is not None:
                    data = revision.version(self.related_model_instance, rev=rev)
                    pks = data['related'].get(self.related_model_attname, [])
                    self.core_filters = {'pk__in': pks}

                return super(VersionsRelatedManager, self).get_query_set(*args, **kwargs)
        new_manager = VersionsRelatedManager()
        new_manager.__dict__ = manager.__dict__
        return new_manager

class VersionsReverseManyRelatedObjectsDescriptor(related.ReverseManyRelatedObjectsDescriptor):
    def __get__(self, instance, instance_type=None):
        if instance is None:
            return self

        # Dynamically create a class that subclasses the related
        # model's default manager.
        rel_model=self.field.rel.to
        superclass = rel_model._default_manager.__class__
        RelatedManager = related.create_many_related_manager(superclass, self.field.rel.through)

        class VersionsRelatedManager(RelatedManager):
            def __get_staged_changes(self):
                return self.related_model_instance._versions_staged_changes.get(self.related_model_attname, revision.data(self.related_model_instance)['related'][self.related_model_attname])

            def add(self, *args, **kwargs):
                if self.related_model_instance._versions_status == VERSIONS_STATUS_STAGED_EDITS:
                    changes = self.__get_staged_changes() + [ (hasattr(x, 'pk') and x.pk or x) for x in args ]
                    self.related_model_instance._versions_staged_changes[self.related_model_attname] = changes
                else:
                    super(VersionsRelatedManager, self).add(*args, **kwargs)
                revision.stage(self.related_model_instance)

            def remove(self, *args, **kwargs):
                if self.related_model_instance._versions_status == VERSIONS_STATUS_STAGED_EDITS:
                    changes = self.__get_staged_changes()
                    removed = [ (hasattr(x, 'pk') and x.pk or x) for x in args ]
                    self.related_model_instance._versions_staged_changes[self.related_model_attname] = [ x for x in changes if x not in removed ]
                else:
                    super(VersionsRelatedManager, self).remove(*args, **kwargs)
                revision.stage(self.related_model_instance)

            def clear(self, *args, **kwargs):
                if self.related_model_instance._versions_status == VERSIONS_STATUS_STAGED_EDITS:
                    self.related_model_instance._versions_staged_changes[self.related_model_attname] = []
                else:
                    super(VersionsRelatedManager, self).clear(*args, **kwargs)
                revision.stage(self.related_model_instance)

            def get_unfiltered_query_set(self):
                if self.related_model_instance._versions_staged_changes.has_key(self.related_model_attname):
                    self.core_filters = {'pk__in': self.related_model_instance._versions_staged_changes[self.related_model_attname]}
                return super(VersionsRelatedManager, self).get_query_set()

            def get_query_set(self, *args, **kwargs):
                rev = kwargs.get('rev', None)
                if self.related_model_instance is not None:
                    rev = rev and rev or self.related_model_instance._versions_revision

                if rev is not None:
                    data = revision.version(self.related_model_instance, rev=rev)
                    self.core_filters = {'pk__in': data['related'].get(self.related_model_attname)}

                return super(VersionsRelatedManager, self).get_query_set(*args, **kwargs)

        qn = connection.ops.quote_name
        manager = VersionsRelatedManager(
            model=rel_model,
            core_filters={'%s__pk' % self.field.related_query_name(): instance._get_pk_val()},
            instance=instance,
            symmetrical=self.field.rel.symmetrical,
            join_table=qn(self.field.m2m_db_table()),
            source_col_name=qn(self.field.m2m_column_name()),
            target_col_name=qn(self.field.m2m_reverse_name())
        )
        manager.model_attname = self.field.related.get_accessor_name()
        manager.related_model_instance = instance
        manager.related_model_attname = self.field.attname
        return manager
