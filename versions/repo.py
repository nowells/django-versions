from collections import defaultdict
import difflib
import os
try:
    import cPickle as pickle
except ImportError:
    import pickle
import threading

from mercurial.cmdutil import walkchangerevs
from mercurial import context
from mercurial import error
from mercurial import hg
from mercurial import match
from mercurial import ui

from django.conf import settings

# Stores commits during a Managed Version Control session.
_versions = threading.local()

assert hasattr(settings, 'VERSIONS_REPOSITORY_ROOT'), "You must set `VERSIONS_REPOSITORY_ROOT` in your settings.py to be the root of where you would like the django-versions application to checkout working copies of mercurial repositories."

class Versions(object):
    def is_managed(self):
        return getattr(_versions, 'changes', None) is not None

    def start(self):
        if not self.is_managed():
            _versions.changes = defaultdict(dict)

    def finish(self, exception=False):
        if self.is_managed():
            for repo_path, items in _versions.changes.items():
                self.commit(repo_path, items)
            _versions.changes = None

    def stage(self, instance):
        repo_path = self.get_repository_path(instance.__class__, instance._get_pk_val())
        instance_path = self.get_instance_path(instance.__class__, instance._get_pk_val())
        data = self.serialize(instance)
        if self.is_managed():
            _versions.changes[repo_path][instance_path] = data
        else:
            self.commit(repo_path, {instance_path: data})

    def repository(self, repo_path):
        create = not os.path.isdir(repo_path)
        hgui = ui.ui()
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

    def commit(self, repo_path, items):
        if items:
            repository = self.repository(repo_path)

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
                ctx = context.memctx(
                    repo=repository,
                    parents=('tip', None),
                    text="Commit Message",
                    files=items.keys(),
                    filectxfn=file_callback,
                    user="Nowell Strite <nowell@strite.org>",
                    )

                repository.commitctx(ctx)

                hg.update(repository, repository['tip'].node())
            finally:
                lock.release()

    def get_repository_path(self, cls, pk):
        return os.path.join(settings.VERSIONS_REPOSITORY_ROOT, cls.__module__.rsplit('.')[-2])

    def get_instance_path(self, cls, pk):
        return os.path.join(cls.__module__.lower(), cls.__name__.lower(), str(pk))

    def serialize(self, instance):
        return pickle.dumps(self.data(instance))

    def deserialize(self, data):
        return pickle.loads(data)

    def data(self, instance):
        fields = [ x for x in instance._meta.fields if not x.primary_key ]

        #if self.include is not None:
        #    fields = [ x for x in fields if x.name in self.include ]
        #elif self.exclude is not None:
        #    fields = [ x for x in fields if x.name not in self.exclude ]

        field_names = [ x.name for x in fields ]
        return dict([ (x[0], x[1],) for x in instance.__dict__.items() if x[0] in field_names ])

    def _revision(self, cls, pk, rev='tip'):
        repo_path = self.get_repository_path(cls, pk)
        instance_path = self.get_instance_path(cls, pk)
        print 'Fetching revision %s for %s from %s' % (rev, instance_path, repo_path)
        repository = self.repository(repo_path)
        fctx = repository.filectx(instance_path, rev)
        raw_data = fctx.data()
        return self.deserialize(raw_data)

    def revision(self, instance, rev='tip'):
        try:
            return self._revision(instance.__class__, instance._get_pk_val(), rev=rev)
        except LookupError:
            return self.data(instance)

    def revisions(self, instance):
        repo_path = self.get_repository_path(instance.__class__, instance._get_pk_val())
        instance_path = self.get_instance_path(instance.__class__, instance._get_pk_val())
        repository = self.repository(repo_path)
        instance_match = match.exact(repository.root, repository.getcwd(), [instance_path])
        change_contexts = walkchangerevs(repository, instance_match, {'rev': None}, lambda ctx, fns: ctx)
        return change_contexts

    def diff(self, instance, rev0, rev1=None):
        inst0 = self.revision(instance, rev0)
        if rev1 is None:
            inst1 = self.data(instance)
        else:
            inst1 = self.revision(instance, rev1)
        keys = list(set(inst0.keys() + inst1.keys()))
        difference = {}
        for key in keys:
            difference[key] = ''.join(difflib.unified_diff(repr(inst0.get(key, '')), repr(inst1.get(key, ''))))
        return difference
