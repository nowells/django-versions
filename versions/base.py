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

try:
    from functools import wraps
except ImportError:
    from django.utils.functional import wraps  # Python 2.3, 2.4 fallback.

from django.conf import settings
from django.contrib.auth.models import AnonymousUser, User
from django.core.exceptions import ImproperlyConfigured
from django.db.models.fields import related

from versions.exceptions import VersionDoesNotExist, VersionsMultipleParents, VersionsManagementException
from versions.utils import load_backend

__all__ = ('revision',)

if not hasattr(settings, 'VERSIONS_REPOSITORIES'):
    raise ImproperlyConfigured("You must configure `VERSIONS_REPOSITORIES` in your settings.py")
elif not isinstance(settings.VERSIONS_REPOSITORIES, dict):
    raise ImproperlyConfigured("`VERSIONS_REPOSITORIES` must be a dictionary.")
elif not 'default' in settings.VERSIONS_REPOSITORIES:
    raise ImproperlyConfigured("You must always configure a `default` repository in `VERSIONS_REPOSITORIES`")

class RevisionState(threading.local):
    def __init__(self):
        self.reset()

    def reset(self):
        self.staged_objects = defaultdict(dict)
        self.pending_objects = set([])
        self.pending_many_to_many_updates = defaultdict(list)
        self.pending_related_updates = defaultdict(list)
        self.user = None
        self.message = ""
        self.depth = 0
        self.is_invalid = False
        self.is_finishing = False

class RevisionManager(object):
    __slots__ = ("__weakref__", "_repos", "_state",)

    def __init__(self):
        self._state = RevisionState()
        self._repos = {}

    def is_active(self):
        return bool(self._state.depth > 0) or self._state.is_finishing

    def assert_active(self):
        """Checks for an active revision, throwning an exception if none."""
        if not self.is_active():
            raise VersionsManagementException("There is no active revision transaction for this thread.")

    def start(self):
        self._state.depth += 1

    def invalidate(self):
        self.assert_active()
        self._state.is_invalid = True

    def is_invalid(self):
        return self._state.is_invalid

    def finish(self):
        self.assert_active()
        self._state.depth -= 1
        revisions = {}
        # Handle end of revision conditions here.
        if self._state.depth == 0:
            self._state.is_finishing = True
            try:
                if not self.is_invalid() and (self._state.pending_objects or self._state.staged_objects):
                    while self._state.pending_objects:
                        item = self._state.pending_objects.pop()
                        self.stage(item)

                    for repo, items in self._state.staged_objects.items():
                        revisions[repo] = self[repo].commit(items)
            finally:
                self._state.reset()
        return revisions

    def stage_related_update(self, instance, field_name, old, new):
        self.assert_active()

        related_field = instance._meta.get_field(field_name).related.get_accessor_name()
        if old is not None:
            self._state.pending_objects.add(old)
            self._state.related_updates[old].append(['remove', related_field, instance.pk])
        self._state.pending_objects.add(new)
        self._state.related_updates[new].append(['add', related_field, instance.pk])

    def stage(self, instance):
        self.assert_active()

        repo = self.repository_path(instance.__class__, instance._get_pk_val())
        item = self.item_path(instance.__class__, instance._get_pk_val())

        self._state.pending_objects.discard(instance)

        data = self.serialize(instance)
        self._state.staged_objects[repo][item] = data

    def serialize(self, instance):
        return pickle.dumps(self.data(instance))

    def deserialize(self, data):
        return pickle.loads(data)

    def data(self, instance):
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

        related_removals = defaultdict(set)
        related_additions = defaultdict(set)
        for action, field, item in self._state.related_updates.get(instance, []):
            if action == 'add':
                related_removals[field].discard(item)
                related_additions[field].add(item)
            else:
                related_additions[field].discard(item)
                related_removals[field].add(item)

        for name, data in name_map.items():
            if isinstance(data[0], (related.RelatedObject, related.ManyToManyField)):
                manager = getattr(instance, name)
                if hasattr(manager, 'get_unfiltered_query_set'):
                    manager = manager.get_unfiltered_query_set()
                related_items = set([ x['pk'] for x in manager.values('pk') ])
                related_items = related_items.difference(related_removals.get(name, []))
                related_items = related_items.union(related_additions.get(name, []))
                related_data[name] = list(related_items)

        return {
            'field': field_data,
            'related': related_data,
            }

    def _version(self, cls, pk, rev=None):
        repo = self.repository_path(cls, pk)
        item = self.item_path(cls, pk)
        return self.deserialize(self[repo].version(item, rev=rev))

    def version(self, instance, rev=None):
        return self._version(instance.__class__, instance._get_pk_val(), rev=rev)

    def _versions(self, cls, pk):
        repo = self.repository_path(cls, pk)
        item = self.item_path(cls, pk)
        return self[repo].versions(item)

    def versions(self, instance):
        return self._versions(instance.__class__, instance._get_pk_val())

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
        return cls._versions_options.repository

    def item_path(self, cls, pk):
        return os.path.join(cls.__module__.lower(), cls.__name__.lower(), str(pk))

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
            self._state.user = AnonymousUser()
        elif isinstance(val, AnonymousUser):
            self._state.user = val
        elif isinstance(val, User):
            self._state.user = val
        else:
            try:
                self._state.user = User.objects.get(pk=val)
            except User.DoesNotExist:
                self._state.user = AnonymousUser()
            except ValueError:
                self._state.user = AnonymousUser()

    def _get_user(self):
        if self._state.user is None:
            return AnonymousUser()
        return self._state.user

    user = property(_get_user, _set_user)

    def _set_message(self, val):
        self._state.message = val

    def _get_message(self):
        if not self._state.message:
            return u'There was no commit message specified.'
        else:
            return self._state.message

    message = property(_get_message, _set_message)


    def __enter__(self):
        """Enters a block of revision management."""
        self.start()

    def __exit__(self, exc_type, exc_value, traceback):
        """Leaves a block of revision management."""
        if exc_type is not None:
            self.invalidate()
        self.finish()
        return False

    def commit_on_success(self, func):
        def _commit_on_success(*args, **kwargs):
            self.start()
            try:
                try:
                    result = func(*args, **kwargs)
                except:
                    self.invalidate()
                    raise
            finally:
                self.finish()
            return result
        return wraps(func)(_commit_on_success)

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
        if not hasattr(self, '_user'):
            val = self._commit.user()
            if val is None:
                user = AnonymousUser()
            else:
                try:
                    self._user = User.objects.get(pk=val)
                except User.DoesNotExist:
                    self._user = AnonymousUser()
                except ValueError:
                    self._user = AnonymousUser()
        return self._user

    @property
    def message(self):
        return self._commit.description()

    @property
    def date(self):
        t, tz = self._commit.date()
        return datetime.datetime.fromtimestamp(time.mktime(time.gmtime(t - tz)))


revision = RevisionManager()
