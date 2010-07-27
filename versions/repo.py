from collections import defaultdict
import difflib
import os
try:
    import cPickle as pickle
except ImportError:
    import pickle
import threading

import datetime
import time

from mercurial.cmdutil import walkchangerevs
from mercurial import context
from mercurial import error
from mercurial import hg
from mercurial import match
from mercurial import node
from mercurial import ui

from django.conf import settings
from django.db.models.fields import related
from versions.exceptions import VersionDoesNotExist

# Stores commits during a Managed Version Control session.
_versions = threading.local()

class Version(object):
    def __init__(self, commit):
        t, tz = commit.date()
        self.revision = commit.hex()
        self.user = commit.user()
        self.message = commit.description()
        self.date = datetime.datetime.fromtimestamp(time.mktime(time.gmtime(t - tz)))

    def __unicode__(self):
        return self.revision

    def __str__(self):
        return self.revision

    def __repr__(self):
        return '<Version %s>' % self.revision

    def __eq__(self, other):
        return type(other) == type(self) and other.revision == self.revision

class Versions(object):
    def reset(self):
        if hasattr(_versions, 'changes'):
            delattr(_versions, 'changes')
        if hasattr(_versions, 'user'):
            delattr(_versions, 'user')
        if hasattr(_versions, 'message'):
            delattr(_versions, 'message')

    def is_managed(self):
        return hasattr(_versions, 'changes')

    def start(self):
        if not self.is_managed():
            self.reset()
            _versions.changes = defaultdict(dict)

    def finish(self, exception=False):
        revisions = {}
        if self.is_managed():
            for repo_path, items in _versions.changes.items():
                revisions[repo_path] = self.commit(repo_path, items)
            self.reset()
        return revisions

    def stage(self, instance, related_updates=None):
        repo_path = self.get_repository_path(instance.__class__, instance._get_pk_val())
        instance_path = self.get_instance_path(instance.__class__, instance._get_pk_val())
        data = self.serialize(instance, related_updates=related_updates)
        revision = None
        if self.is_managed():
            _versions.changes[repo_path][instance_path] = data
        else:
            revision = self.commit(repo_path, {instance_path: data})
        return revision

    def _set_user(self, user):
        _versions.user = user
    def _get_user(self):
        return getattr(_versions, 'user', 'Anonymous')
    user = property(_get_user, _set_user)

    def _set_message(self, text):
        _versions.message = text
    def _get_message(self):
        return getattr(_versions, 'message', 'There was no commit message specified.')
    message = property(_get_message, _set_message)

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

            # We want to capture all mercurial output for these commits.
            repository.ui.pushbuffer()

            lock = repository.lock()
            try:
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
                return revision
            finally:
                lock.release()
                repository.ui.popbuffer()

    def get_repository_path(self, cls, pk):
        return os.path.join(settings.VERSIONS_REPOSITORY_ROOT, cls.__module__.rsplit('.')[-2])

    def get_instance_path(self, cls, pk):
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
        repo_path = self.get_repository_path(cls, pk)
        instance_path = self.get_instance_path(cls, pk)
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
        repo_path = self.get_repository_path(cls, pk)
        instance_path = self.get_instance_path(cls, pk)
        repository = self.repository(repo_path)
        instance_match = match.exact(repository.root, repository.getcwd(), [instance_path])
        change_contexts = walkchangerevs(repository, instance_match, {'rev': None}, lambda ctx, fns: ctx)
        return [ Version(x) for x in change_contexts ]

    def revisions(self, instance):
        return self._revisions(instance.__class__, instance._get_pk_val())

    def diff(self, instance, rev0, rev1=None, raw=True):
        inst0 = self.version(instance, rev0)
        if rev1 is None:
            inst1 = self.data(instance)
        else:
            inst1 = self.version(instance, rev1)

        differences = {
            'field': {},
            'related': {},
            }

        html_diff = None
        if not raw:
            html_diff = difflib.HtmlDiff(wrapcolumn=50)
            html_diff._table_template = """
<table class="diff" id="difflib_chg_%(prefix)s_top" cellspacing="0" cellpadding="0" rules="groups" width="800">
    <colgroup width="10"></colgroup>
    <colgroup width="20"></colgroup>
    <colgroup width="370"></colgroup>
    <colgroup width="10"></colgroup>
    <colgroup width="20"></colgroup>
    <colgroup width="370"></colgroup>
    %(header_row)s
    <tbody>
        %(data_rows)s
    </tbody>
</table>
"""
        for area in ('field', 'related',):
            keys = list(set(inst0[area].keys() + inst1[area].keys()))
            for key in keys:
                val0 = repr(inst0[area].get(key, ''))
                val1 = repr(inst1[area].get(key, ''))

                if raw:
                    difference = ''.join(difflib.unified_diff(val0, val1))
                else:
                    difference = html_diff.make_table(val0.splitlines(), val1.splitlines(), fromdesc=rev0, todesc=rev1, context=False)

                differences[area][key] = difference
        return differences

versions = Versions()
