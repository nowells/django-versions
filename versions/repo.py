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

class LogUI(ui.ui):
    def __init__(self, *args, **kwargs):
        self.log = logging.getLogger('versions')
        super(LogUI, self).__init__(*args, **kwargs)

    def write(self, *args, **opts):
        if self._buffers:
            self._buffers[-1].extend([str(a) for a in args])
        else:
            for a in args:
                self.log.info(str(a))

    def write_err(self, *args, **opts):
        for a in args:
            self.log.error(str(a))

    def flush(self):
        pass

    def interactive(self):
        return False

    def formatted(self):
        return False

    def _readline(self, prompt=''):
        raise Exception('Unable to readline on a non-interactive client.')

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
    user = 'Anonymous'
    message = 'There was no commit message specified.'

    def __init__(self):
        self.reset()

    def reset(self):
        self.changes = None
        self.user = 'Anonymous'
        self.message = 'There was no commit message specified.'

    def is_managed(self):
        return self.changes is not None

    def start(self):
        if not self.is_managed():
            self.reset()
            self.changes = defaultdict(dict)

    def finish(self, exception=False):
        revisions = {}
        if self.is_managed():
            for repo_path, items in self.changes.items():
                revisions[repo_path] = self.commit(repo_path, items)
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
            revision = self.commit(repo_path, {instance_path: data})
        return revision

    def repository(self, path):
        repo_path = os.path.join(settings.VERSIONS_REPOSITORY_ROOT, path)
        create = not os.path.isdir(repo_path)
        hgui = LogUI()
        hgui.setconfig('ui', 'interactive', 'off')
        if not os.path.exists(os.path.dirname(repo_path)):
            os.makedirs(os.path.dirname(repo_path))
        try:
            repository = hg.repository(hgui, repo_path, create=create)
        except error.RepoError:
            repository = hg.repository(hgui, repo_path)
        except Exception, e:
            raise

        return repository

    def remote_repository(self, path):
        remote = getattr(settings, 'VERSIONS_REMOTE_REPOSITORY_ROOT', None)
        if remote:
            repo_path = os.path.join(settings.VERSIONS_REMOTE_REPOSITORY_ROOT, path)
            hgui = LogUI()
            hgui.setconfig('ui', 'interactive', 'off')
            repository = hg.repository(hgui, repo_path)
            return repository
        return None

    def commit(self, repo_path, items):
        if items:
            repository = self.repository(repo_path)
            remote_repository = self.remote_repository(repo_path)

            def file_callback(repo, memctx, path):
                return context.memfilectx(
                    path=path,
                    data=items[path],
                    islink=False,
                    isexec=False,
                    copied=False,
                    )

            lock = repository.lock()
            try:
                if remote_repository:
                    repository.pull(remote_repository)

                ctx = context.memctx(
                    repo=repository,
                    parents=('tip', None),
                    text=self.message,
                    files=items.keys(),
                    filectxfn=file_callback,
                    user=self.user,
                    )
                revision = node.hex(repository.commitctx(ctx))
                # TODO: if we want the working copy of the repository to be updated as well add logic to enable this.
                # hg.update(repository, repository['tip'].node())

                if remote_repository:
                    repository.push(remote_repository)
                return revision
            finally:
                lock.release()

    def repository_path(self, cls, pk):
        return cls.__module__.rsplit('.')[-2]

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

    def _version(self, cls, pk, rev='tip'):
        repo_path = self.repository_path(cls, pk)
        instance_path = self.instance_path(cls, pk)
        if not rev:
            raise VersionDoesNotExist('Revision `%s` does not exist for %s in %s' % (rev, instance_path, repo_path))

        repository = self.repository(repo_path)
        fctx = repository.filectx(instance_path, rev)
        try:
            raw_data = fctx.data()
        except error.LookupError:
            raise VersionDoesNotExist('Revision `%s` does not exist for %s in %s' % (rev, instance_path, repo_path))
        return self.deserialize(raw_data)

    def version(self, instance, rev='tip'):
        return self._version(instance.__class__, instance._get_pk_val(), rev=rev)

    def _revisions(self, cls, pk):
        repo_path = self.repository_path(cls, pk)
        instance_path = self.instance_path(cls, pk)
        repository = self.repository(repo_path)
        instance_match = match.exact(repository.root, repository.getcwd(), [instance_path])
        change_contexts = walkchangerevs(repository, instance_match, {'rev': None}, lambda ctx, fns: ctx)
        for change_context in change_contexts:
            yield Version(change_context)

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
