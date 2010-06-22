from django.db import connection
from django.db.models.fields import related

from versions.repo import Versions

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
                result = super(VersionsRelatedManager, self).add(*args, **kwargs)
                vc = Versions()
                vc.stage(self.related_model_instance)
                return result

            def remove(self, *args, **kwargs):
                result = super(VersionsRelatedManager, self).remove(*args, **kwargs)
                vc = Versions()
                vc.stage(self.related_model_instance)
                return result

            def clear(self, *args, **kwargs):
                result = super(VersionsRelatedManager, self).clear(*args, **kwargs)
                vc = Versions()
                vc.stage(self.related_model_instance)
                return result

            def get_query_set(self, revision=None):
                if self.related_model_instance is not None:
                    revision = revision and revision or self.related_model_instance._versions_revision

                if revision is not None:
                    vc = Versions()
                    data = vc.version(self.related_model_instance, rev=revision)
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
