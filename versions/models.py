import django

from django.db import models
from django.db.models.fields import related

from versions.base import revision
from versions.constants import VERSIONS_STATUS_CHOICES, VERSIONS_STATUS_PUBLISHED, VERSIONS_STATUS_DELETED, VERSIONS_STATUS_STAGED_EDITS, VERSIONS_STATUS_STAGED_DELETE
from versions.exceptions import VersionsException
from versions.managers import VersionsManager

class VersionsOptions(object):
    @classmethod
    def contribute_to_class(klass, cls, name):
        include = getattr(klass, 'include', [])
        exclude = getattr(klass, 'exclude', [])

        invalid_excludes = set(['_versions_status']).intersection(exclude)
        if invalid_excludes:
            raise VersionsException('You cannot include `%s` in a VersionOptions exclude.' % ', '.join(invalid_excludes))

        cls._versions_options = VersionsOptions()
        cls._versions_options.include = include
        cls._versions_options.exclude = exclude
        cls._versions_options.core_include = ['_versions_status']
        cls._versions_options.repository = getattr(klass, 'repository', 'default')

class VersionsModel(models.Model):
    _versions_status = models.PositiveIntegerField(choices=VERSIONS_STATUS_CHOICES, default=VERSIONS_STATUS_PUBLISHED)
    def versions_status(self):
        return self._versions_status
    versions_status = property(versions_status)

    objects = VersionsManager()

    class Meta:
        abstract = True

    class Versions(VersionsOptions):
        exclude = []
        include = []

    # Used to store the revision of the model.
    _versions_revision = None

    def __init__(self, *args, **kwargs):
        self._versions_revision = None
        super(VersionsModel, self).__init__(*args, **kwargs)

    def _save_base(self, *args, **kwargs):
        is_new = self._get_pk_val() is None
        super(VersionsModel, self).save(*args, **kwargs)

        if is_new:
            try:
                name_map = self._meta._name_map
            except AttributeError:
                name_map = self._meta.init_name_map()

            for name, data in name_map.items():
                if isinstance(data[0], related.ForeignKey):
                    related_field = self._meta.get_field(name).related.get_accessor_name()
                    obj = getattr(self, name, None)
                    if obj:
                        revision.stage_related_updates(obj, related_field, 'add', [self], symmetrical=False)

    def save(self, *args, **kwargs):
        if (self._get_pk_val() is None or self._versions_status in (VERSIONS_STATUS_PUBLISHED, VERSIONS_STATUS_DELETED)):
            self._save_base(*args, **kwargs)
        revision.stage(self)

    def save_base(self, *args, **kwargs):
        # We want to be paranoid about not issuing inserts with pk values
        # which are already in the database even if they're for deleted values
        # which will not normally be seen by .exists():
        if django.VERSION >= (1, 2):
            pk = self._get_pk_val()
            if not kwargs.get("force_update") \
                   and pk is not None \
                   and self._base_manager.get_query_set(bypass=True).filter(pk=pk).exists():
                kwargs['force_update'] = True

        return super(VersionsModel, self).save_base(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self._versions_status in (VERSIONS_STATUS_STAGED_EDITS, VERSIONS_STATUS_STAGED_DELETE,):
            self._versions_status = VERSIONS_STATUS_STAGED_DELETE
        else:
            self._versions_status = VERSIONS_STATUS_DELETED
        self.save(*args, **kwargs)

    def commit(self):
        if self._versions_status == VERSIONS_STATUS_STAGED_DELETE:
            self._versions_status = VERSIONS_STATUS_DELETED
        elif self._versions_status == VERSIONS_STATUS_STAGED_EDITS:
            self._versions_status = VERSIONS_STATUS_PUBLISHED

        # We don't want to call our main save method, because we want to delay
        # staging the state of this model until we set the state of all unpublihsed manytomany edits.
        self._save_base()

        if self._versions_revision is None:
            data = revision.data(self)
        else:
            data = revision.version(self, rev=self._versions_revision)

        for name, ids in data['related'].items():
            try:
                field = self._meta.get_field_by_name(name)[0]
            except:
                pass
            else:
                if isinstance(field, related.ManyToManyField):
                    related_manager = getattr(self, name)
                    if issubclass(related_manager.model, VersionsModel):
                        existing_ids = set(list(related_manager.get_query_set(bypass=True, bypass_filter=True).values_list('pk', flat=True)))
                    else:
                        existing_ids = set(list(related_manager.values_list('pk', flat=True)))

                    if self in revision._state.pending_related_updates and name in revision._state.pending_related_updates[self]:
                        updated_ids = revision._state.pending_related_updates[self][name]
                    else:
                        updated_ids = ids

                    if existing_ids.symmetric_difference(updated_ids):
                        setattr(self, name, updated_ids)

        revision.stage(self)

    def stage(self):
        self._versions_status = VERSIONS_STATUS_STAGED_EDITS
        self.save()
