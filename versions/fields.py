from django.db import connection
from django.db.models.fields import related
from django.db.models import signals
from versions.repo import versions

def stage_related_models(sender, instance, created, **kwargs):
    """
    This signal handler is used to alert objects to changes in the ForeignKey of related objects.
    We capture both the creation of a new ForeignKey relationship, as well as the removal or changing
    of an existing ForeignKey relationship.
    """
    for field, models in instance._versions_related_updates.items():
        for model in models:
            versions.stage(model)

class VersionsForeignKey(related.ForeignKey):
    """
    A field used to allow VersionsModel objects to track non-versioned ForeignKey objects associated with
    a model at a given revision.
    """
    def contribute_to_class(self, cls, name):
        cls._versions_related_updates = {}
        super(VersionsForeignKey, self).contribute_to_class(cls, name)
        setattr(cls, self.name, VersionsReverseSingleRelatedObjectDescriptor(self))

    def contribute_to_related_class(self, cls, related):
        super(VersionsForeignKey, self).contribute_to_related_class(cls, related)
        setattr(cls, related.get_accessor_name(), VersionsForeignRelatedObjectsDescriptor(related))
        signals.post_save.connect(stage_related_models, sender=related.model, dispatch_uid='versions_foreignkey_related_object_update')

class VersionsReverseSingleRelatedObjectDescriptor(related.ReverseSingleRelatedObjectDescriptor):
    def __set__(self, instance, value):
        old_value = getattr(instance, self.field.name, None)
        result = super(VersionsReverseSingleRelatedObjectDescriptor, self).__set__(instance, value)
        if old_value != value:
            instance._versions_related_updates[self.field.name] = [ x for x in [old_value, value] if x is not None ]
        return result

class VersionsForeignRelatedObjectsDescriptor(related.ForeignRelatedObjectsDescriptor):
    def __get__(self, instance, instance_type=None):
        if instance is None:
            return self

        manager = super(VersionsForeignRelatedObjectsDescriptor, self).__get__(instance, instance_type)
        class VersionsRelatedManager(manager.__class__):
            def get_unfiltered_query_set(self):
                return super(VersionsRelatedManager, self).get_query_set()

            def get_query_set(self, revision=None):
                if self.related_model_instance is not None and hasattr(self.related_model_instance, '_versions_revision'):
                    revision = self.related_model_instance._versions_revision

                if revision is not None:
                    data = versions.version(self.related_model_instance, rev=revision)
                    pks = data['related'].get(self.related_model_field_name, [])
                    self.core_filters = {'pk__in': pks}

                return super(VersionsRelatedManager, self).get_query_set()
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
        RelatedManager = related.create_many_related_manager(superclass, self.field.rel.through)

        class VersionsRelatedManager(RelatedManager):
            def add(self, *args, **kwargs):
                super(VersionsRelatedManager, self).add(*args, **kwargs)
                versions.stage(self.related_model_instance)

            def remove(self, *args, **kwargs):
                super(VersionsRelatedManager, self).remove(*args, **kwargs)
                versions.stage(self.related_model_instance)

            def clear(self, *args, **kwargs):
                super(VersionsRelatedManager, self).clear(*args, **kwargs)
                versions.stage(self.related_model_instance)

            def get_unfiltered_query_set(self):
                return super(VersionsRelatedManager, self).get_query_set()

            def get_query_set(self, revision=None):
                if self.related_model_instance is not None:
                    revision = revision and revision or self.related_model_instance._versions_revision

                if revision is not None:
                    data = versions.version(self.related_model_instance, rev=revision)
                    self.core_filters = {'pk__in': data['related'].get(self.related_model_field_name)}

                results = super(VersionsRelatedManager, self).get_query_set()
                return results

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
        manager.model_field_name = self.field.m2m_reverse_name()
        manager.related_model_instance = instance
        manager.related_model_field_name = self.field.attname
        return manager
