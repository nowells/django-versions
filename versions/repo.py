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

from mercurial.cmdutil import walkchangerevs
from mercurial import context
from mercurial import error
from mercurial import hg
from mercurial import match
from mercurial import node
from mercurial import ui

from django.conf import settings
from django.db.models.fields import related
from versions.exceptions import VersionDoesNotExist, VersionsMultipleParents

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

class Versions(threading.local):
    changes = None

    def __init__(self):
        from versions.backends.hg import MercurialRepository
        self.repositories = {
            'default': MercurialRepository(settings.VERSIONS_REPOSITORY_ROOT),
            }
        super(Versions, self).__init__()

    def is_managed(self):
        return self.changes is not None

    def reset(self):
        self.changes = None
        for name, repo in self.repositories.items():
            repo.reset()

    def start(self):
        if not self.is_managed():
            self.reset()
            self.changes = defaultdict(dict)

    def finish(self, exception=False):
        revisions = {}
        if self.is_managed():
            for repo_path, items in self.changes.items():
                revisions[repo_path] = self.repositories[repo_path].commit(items)
            self.reset()
        return revisions

    def stage(self, instance, related_updates=None):
        repo_path = self.repository_path(instance.__class__, instance._get_pk_val())
        instance_path = self.instance_path(instance.__class__, instance._get_pk_val())
        data = self.serialize(instance, related_updates=related_updates)
        revision = None
        if self.is_managed():
            self.changes[repo_path][instance_path] = data
        else:
            revision = self.repositories[repo_path].commit({instance_path: data})
        return revision

    def repository_path(self, cls, pk):
        return 'default'

    def instance_path(self, cls, pk):
        return os.path.join(cls.__module__.lower(), cls.__name__.lower(), str(pk))

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
        repo_path = self.repository_path(cls, pk)
        instance_path = self.instance_path(cls, pk)
        return self.deserialize(self.repositories[repo_path].version(instance_path, revision=revision))

    def version(self, instance, revision=None):
        return self._version(instance.__class__, instance._get_pk_val(), revision=revision)

    def _revisions(self, cls, pk):
        repo_path = self.repository_path(cls, pk)
        instance_path = self.instance_path(cls, pk)
        return self.repositories[repo_path].revisions(instance_path)

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

versions = Versions()
