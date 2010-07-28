import django
from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
from django.db.models.fields import related
from django.db.models import signals

from versions.constants import VERSIONS_STATUS_STAGED_EDITS, VERSIONS_STATUS_PUBLISHED
from versions.repo import versions

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
            versions.stage(old_related_model, related_updates={'removed': {related_field: [instance]}})
        versions.stage(new_related_model, related_updates={'added': {related_field: [instance]}})

class VersionsForeignKey(related.ForeignKey):
    """
    A field used to allow VersionsModel objects to track non-versioned ForeignKey objects associated with
    a model at a given revision.
    """
    def contribute_to_class(self, cls, name):
        super(VersionsForeignKey, self).contribute_to_class(cls, name)
        setattr(cls, self.name, VersionsReverseSingleRelatedObjectDescriptor(self))

    def contribute_to_related_class(self, cls, related):
        super(VersionsForeignKey, self).contribute_to_related_class(cls, related)
        setattr(cls, related.get_accessor_name(), VersionsForeignRelatedObjectsDescriptor(related))
        signals.post_save.connect(stage_related_models, sender=related.model, dispatch_uid='versions_foreignkey_related_object_update')

class VersionsReverseSingleRelatedObjectDescriptor(related.ReverseSingleRelatedObjectDescriptor):
    def __set__(self, instance, value):
        try:
            old_value = getattr(instance, self.field.name, None)
        except ObjectDoesNotExist:
            old_value = None

        result = super(VersionsReverseSingleRelatedObjectDescriptor, self).__set__(instance, value)
        if old_value != value:
            instance._versions_related_updates[self.field.name] = [old_value, value]
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
                revision = kwargs.get('revision', None)
                if self.related_model_instance is not None and hasattr(self.related_model_instance, '_versions_revision'):
                    revision = self.related_model_instance._versions_revision

                if revision is not None:
                    data = versions.version(self.related_model_instance, rev=revision)
                    pks = data['related'].get(self.related_model_attname, [])
                    self.core_filters = {'pk__in': pks}

                return super(VersionsRelatedManager, self).get_query_set(*args, **kwargs)
        new_manager = VersionsRelatedManager()
        new_manager.__dict__ = manager.__dict__
        return new_manager

class VersionsManyToManyField(related.ManyToManyField):
    """
    A field used to allow VersionsModel objects to track non-versioned ManyToManyField objects associated with
    a model at a given revision.
    """
    def contribute_to_class(self, cls, name):
        super(VersionsManyToManyField, self).contribute_to_class(cls, name)
        setattr(cls, self.name, VersionsReverseManyRelatedObjectsDescriptor(self))

class VersionsReverseManyRelatedObjectsDescriptor(related.ReverseManyRelatedObjectsDescriptor):
    def __get__(self, instance, instance_type=None):
        if instance is None:
            return self

        # Dynamically create a class that subclasses the related
        # model's default manager.
        rel_model=self.field.rel.to
        superclass = rel_model._default_manager.__class__
        if django.VERSION < (1, 2):
            RelatedManager = related.create_many_related_manager(superclass, self.field.rel.through)
        else:
            RelatedManager = related.create_many_related_manager(superclass, self.field.rel)

        class VersionsRelatedManager(RelatedManager):
            def __get_staged_changes(self):
                return self.related_model_instance._versions_staged_changes.get(self.related_model_attname, versions.data(self.related_model_instance)['related'][self.related_model_attname])

            def add(self, *args, **kwargs):
                if self.related_model_instance._versions_status == VERSIONS_STATUS_STAGED_EDITS:
                    changes = self.__get_staged_changes() + [ (hasattr(x, 'pk') and x.pk or x) for x in args ]
                    self.related_model_instance._versions_staged_changes[self.related_model_attname] = changes
                else:
                    super(VersionsRelatedManager, self).add(*args, **kwargs)
                versions.stage(self.related_model_instance)

            def remove(self, *args, **kwargs):
                if self.related_model_instance._versions_status == VERSIONS_STATUS_STAGED_EDITS:
                    changes = self.__get_staged_changes()
                    removed = [ (hasattr(x, 'pk') and x.pk or x) for x in args ]
                    self.related_model_instance._versions_staged_changes[self.related_model_attname] = [ x for x in changes if x not in removed ]
                else:
                    super(VersionsRelatedManager, self).remove(*args, **kwargs)
                versions.stage(self.related_model_instance)

            def clear(self, *args, **kwargs):
                if self.related_model_instance._versions_status == VERSIONS_STATUS_STAGED_EDITS:
                    self.related_model_instance._versions_staged_changes[self.related_model_attname] = []
                else:
                    super(VersionsRelatedManager, self).clear(*args, **kwargs)
                versions.stage(self.related_model_instance)

            def get_unfiltered_query_set(self):
                if self.related_model_instance._versions_staged_changes.has_key(self.related_model_attname):
                    self.core_filters = {'pk__in': self.related_model_instance._versions_staged_changes[self.related_model_attname]}
                return super(VersionsRelatedManager, self).get_query_set()

            def get_query_set(self, *args, **kwargs):
                revision = kwargs.get('revision', None)
                if self.related_model_instance is not None:
                    revision = revision and revision or self.related_model_instance._versions_revision

                if revision is not None:
                    data = versions.version(self.related_model_instance, rev=revision)
                    self.core_filters = {'pk__in': data['related'].get(self.related_model_attname)}

                return super(VersionsRelatedManager, self).get_query_set(*args, **kwargs)

        qn = connection.ops.quote_name

        if django.VERSION < (1, 2):
            manager = VersionsRelatedManager(
                model=rel_model,
                core_filters={'%s__pk' % self.field.related_query_name(): instance._get_pk_val()},
                instance=instance,
                symmetrical=self.field.rel.symmetrical,
                join_table=qn(self.field.m2m_db_table()),
                source_col_name=qn(self.field.m2m_column_name()),
                target_col_name=qn(self.field.m2m_reverse_name())
                )
        else:
            manager = VersionsRelatedManager(
                model=rel_model,
                core_filters={'%s__pk' % self.field.related_query_name(): instance._get_pk_val()},
                instance=instance,
                symmetrical=self.field.rel.symmetrical,
                join_table=qn(self.field.m2m_db_table()),
                source_field_name=self.field.m2m_field_name(),
                target_field_name=self.field.m2m_reverse_field_name(),
                )

        manager.model_attname = self.field.related.get_accessor_name()
        manager.related_model_instance = instance
        manager.related_model_attname = self.field.attname
        return manager
