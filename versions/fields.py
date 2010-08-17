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
            related_field = instance._meta.get_field(self.field.name).related.get_accessor_name()

            # If this is a new instance, the save method handles updating related objects once
            # the object has been saved.
            if instance._get_pk_val() is not None:
                if old_value:
                    revision.stage_related_updates(old_value, related_field, 'remove', [instance], symmetrical=False)
                revision.stage_related_updates(value, related_field, 'add', [instance], symmetrical=False)
        return result

class VersionsForeignRelatedObjectsDescriptor(related.ForeignRelatedObjectsDescriptor):
    def __get__(self, instance, instance_type=None):
        if instance is None:
            return self

        manager = super(VersionsForeignRelatedObjectsDescriptor, self).__get__(instance, instance_type)
        class VersionsRelatedManager(manager.__class__):
            def get_query_set(self, *args, **kwargs):
                rev = kwargs.get('rev', None)
                bypass_filter = kwargs.get('bypass_filter', False)
                if self.related_model_instance is not None and hasattr(self.related_model_instance, '_versions_revision'):
                    rev = self.related_model_instance._versions_revision

                if rev is not None and not bypass_filter:
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
            def add(self, *args, **kwargs):
                revision.stage_related_updates(self.related_model_instance, self.related_model_attname, 'add', args)
                if self.related_model_instance._versions_status == VERSIONS_STATUS_PUBLISHED:
                    super(VersionsRelatedManager, self).add(*args, **kwargs)

            def remove(self, *args, **kwargs):
                revision.stage_related_updates(self.related_model_instance, self.related_model_attname, 'remove', args)
                if self.related_model_instance._versions_status == VERSIONS_STATUS_PUBLISHED:
                    super(VersionsRelatedManager, self).remove(*args, **kwargs)

            def clear(self, *args, **kwargs):
                revision.stage_related_updates(self.related_model_instance, self.related_model_attname, 'clear')
                if self.related_model_instance._versions_status == VERSIONS_STATUS_PUBLISHED:
                    super(VersionsRelatedManager, self).clear(*args, **kwargs)

            def get_query_set(self, *args, **kwargs):
                rev = kwargs.get('rev', None)
                bypass_filter = kwargs.get('bypass_filter', False)
                if self.related_model_instance is not None:
                    rev = rev and rev or self.related_model_instance._versions_revision

                if rev is not None and not bypass_filter:
                    self.core_filters = {'pk__in': revision.get_related_object_ids(self.related_model_instance, self.related_model_attname, rev)}

                return super(VersionsRelatedManager, self).get_query_set(*args, **kwargs)

        qn = connection.ops.quote_name
        manager = VersionsRelatedManager(
            model=rel_model,
            core_filters={'%s__pk' % self.field.related_query_name(): instance._get_pk_val()},
            instance=instance,
            symmetrical=(self.field.rel.symmetrical and isinstance(instance, rel_model)),
            join_table=qn(self.field.m2m_db_table()),
            source_col_name=qn(self.field.m2m_column_name()),
            target_col_name=qn(self.field.m2m_reverse_name())
        )
        manager.model_attname = self.field.related.get_accessor_name()
        manager.related_model_instance = instance
        manager.related_model_attname = self.field.attname
        return manager
