from collections import defaultdict
import datetime
import difflib
import logging
import os
import threading
import time

try:
    import cPickle as pickle
except ImportError:
    import pickle

from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ImproperlyConfigured
from django.db.models.fields import related

from versions.exceptions import VersionDoesNotExist, VersionsMultipleParents
from versions.utils import load_backend

__all__ = ('repositories',)

if not hasattr(settings, 'VERSIONS_REPOSITORIES'):
    raise ImproperlyConfigured("You must configure `VERSIONS_REPOSITORIES` in your settings.py")
elif not isinstance(settings.VERSIONS_REPOSITORIES, dict):
    raise ImproperlyConfigured("`VERSIONS_REPOSITORIES` must be a dictionary.")
elif not 'default' in settings.VERSIONS_REPOSITORIES:
    raise ImproperlyConfigured("You must always configure a `default` repository in `VERSIONS_REPOSITORIES`")

class Repositories(threading.local):
    changes = None

    def __init__(self):
        self._repos = {}
        self.reset()

    def is_managed(self):
        return self.changes is not None

    def start(self):
        if not self.is_managed():
            self.reset()
            self.changes = defaultdict(dict)

    def finish(self, exception=False):
        revisions = {}
        if self.is_managed():
            for repo, items in self.changes.items():
                revisions[repo] = self[repo].commit(items)
            self.reset()
        return revisions

    def stage(self, instance, related_updates=None):
        repo = self.repository_path(instance.__class__, instance._get_pk_val())
        item = self.item_path(instance.__class__, instance._get_pk_val())
        data = self.serialize(instance, related_updates=related_updates)
        revision = None
        if self.is_managed():
            self.changes[repo][item] = data
        else:
            revision = self[repo].commit({item: data})
        return revision

    def serialize(self, instance, related_updates=None):
        return pickle.dumps(self.data(instance, related_updates=related_updates))

    def deserialize(self, data):
        return pickle.loads(data)

    def data(self, instance, related_updates=None):
        field_names = [ x.name for x in instance._meta.fields if not x.primary_key ]

        if instance._versions_options.include:
            field_names = [ x for x in field_names if x in (instance._versions_options.include + instance._versions_options.core_include) ]
        elif instance._versions_options.exclude:
            field_names = [ x for x in field_names if x not in instance._versions_options.exclude ]

        field_data = dict([ (x[0], x[1],) for x in instance.__dict__.items() if x[0] in field_names ])
        related_data = {}

        try:
            name_map = instance._meta._name_map
        except AttributeError:
            name_map = instance._meta.init_name_map()

        # TODO: centralize this setup into an object based approach.
        related_updates = related_updates or {}
        for name, data in name_map.items():
            if isinstance(data[0], (related.RelatedObject, related.ManyToManyField)):
                manager = getattr(instance, name)
                if hasattr(manager, 'get_unfiltered_query_set'):
                    manager = manager.get_unfiltered_query_set()
                related_items = set([ x['pk'] for x in manager.values('pk') ])
                related_items = related_items.difference([ x.pk for x in related_updates.get('removed', {}).get(name, []) ])
                related_items = related_items.union([ x.pk for x in related_updates.get('added', {}).get(name, []) ])
                related_data[name] = list(related_items)

        return {
            'field': field_data,
            'related': related_data,
            }

    def _version(self, cls, pk, revision=None):
        repo = self.repository_path(cls, pk)
        item = self.item_path(cls, pk)
        return self.deserialize(self[repo].version(item, revision=revision))

    def version(self, instance, revision=None):
        return self._version(instance.__class__, instance._get_pk_val(), revision=revision)

    def _revisions(self, cls, pk):
        repo = self.repository_path(cls, pk)
        item = self.item_path(cls, pk)
        return self[repo].revisions(item)

    def revisions(self, instance):
        return self._revisions(instance.__class__, instance._get_pk_val())

    def diff(self, instance, rev0, rev1=None):
        inst0 = self.version(instance, rev0)
        if rev1 is None:
            inst1 = self.data(instance)
        else:
            inst1 = self.version(instance, rev1)
        keys = list(set(inst0.keys() + inst1.keys()))
        difference = {}
        for key in keys:
            difference[key] = ''.join(difflib.unified_diff(repr(inst0.get(key, '')), repr(inst1.get(key, ''))))
        return difference

    def repository_path(self, cls, pk):
        return 'default'

    def item_path(self, cls, pk):
        return os.path.join(cls.__module__.lower(), cls.__name__.lower(), str(pk))

    def reset(self):
        self.changes = None
        self.user = None
        self.message = None

    def __getitem__(self, key):
        if key not in self._repos:
            if key in settings.VERSIONS_REPOSITORIES:
                configs = settings.VERSIONS_REPOSITORIES[key]
                if 'backend' not in configs or 'local' not in configs:
                    raise ImproperlyConfigured('You must specify all required conifguration attributes for the `%s` versions backend.' % key)
                backend = load_backend(configs['backend'])
                self._repos[key] = backend.Repository(configs['local'], configs.get('remote', None))
        return self._repos[key]

    def _set_user(self, val):
        if val is None:
            self._user = AnonymousUser()
        elif isinstance(val, User):
            self._user = val
        else:
            try:
                self._user = User.objects.get(pk=val)
            except User.DoesNotExist:
                self._user = AnonymousUser()

    def _get_user(self):
        return self._user

    user = property(_get_user, _set_user)

    def _set_message(self, val):
        if val is None:
            self._message = u'There was no commit message specified.'
        else:
            self._message = val

    def _get_message(self):
        return self._message

    message = property(_get_message, _set_message)


class Version(object):
    def __init__(self, commit):
        self._commit = commit
        self.revision = self._commit.hex()

    def __unicode__(self):
        return self.revision

    def __str__(self):
        return self.revision

    def __repr__(self):
        return '<Version %s>' % self.revision

    def __eq__(self, other):
        return type(other) == type(self) and other.revision == self.revision

    @property
    def parents(self):
        for parent in self._commit.parents():
            yield Version(parent)

    @property
    def parent(self):
        parents = self.parents
        try:
            parent = parents.next()
        except StopIteration:
            return None

        try:
            too_many = parents.next()
        except StopIteration:
            return parent
        else:
            raise VersionsMultipleParents('Found multiple parents for commit %s.' % self.revision)

    @property
    def user(self):
        return self._commit.user()

    @property
    def message(self):
        return self._commit.description()

    @property
    def date(self):
        t, tz = self._commit.date()
        return datetime.datetime.fromtimestamp(time.mktime(time.gmtime(t - tz)))


repositories = Repositories()
