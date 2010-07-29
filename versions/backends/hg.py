from mercurial.cmdutil import walkchangerevs
from mercurial import context
from mercurial import error
from mercurial import hg
from mercurial import match
from mercurial import node
from mercurial import ui

from versions.backends.base import BaseRepository
from versions.repo import Version

class MercurialRepository(BaseRepository):
    @property
    def _local_repo(self):
        if not hasattr(self, '__local_repo'):
            hgui = LogUI()
            hgui.setconfig('ui', 'interactive', 'off')
            self.__local_repo = hg.repository(hgui, self.local)
        return self.__local_repo

    @property
    def _remote_repo(self):
        if not hasattr(self, '__remote_repo'):
            hgui = LogUI()
            hgui.setconfig('ui', 'interactive', 'off')
            self.__remote_repo = hg.repository(hgui, self.remote)
        return self.__remote_repo

    def create(self):
        if not os.path.exists(self.local):
            try:
                hgui = LogUI()
                hgui.setconfig('ui', 'interactive', 'off')
                os.makedirs(os.path.dirname(self.local))
                hg.repository(hgui, self.local, create=True)
            except error.RepoError:
                pass

    def commit(self, items):
        def file_callback(repo, memctx, path):
            return context.memfilectx(
                path=path,
                data=items[path],
                islink=False,
                isexec=False,
                copied=False,
                )

        lock = self._local_repo.lock()
        try:
            if self._remote_repo:
                self._local_repo.pull(self._remote_repo)

            ctx = context.memctx(
                repo=self._local_repo,
                parents=('tip', None),
                text=self.message,
                files=items.keys(),
                filectxfn=file_callback,
                    user=self.user.id,
                )
            revision = node.hex(self._local_repo.commitctx(ctx))
            # TODO: if we want the working copy of the repository to be updated as well add logic to enable this.
            # hg.update(self._local_repo, self._local_repo['tip'].node())
            if self._remote_repo:
                self._local_repo.push(self._remote_repo)

            return revision
        finally:
            lock.release()

    def revisions(self, item):
        instance_match = match.exact(self._local_repo.root, self._local_repo.getcwd(), [item])
        change_contexts = walkchangerevs(self._local_repo, instance_match, {'rev': None}, lambda ctx, fns: ctx)
        for change_context in change_contexts:
            yield Version(change_context)

    def version(self, item, revision=None):
        if revision is None:
            revision = 'tip'

        fctx = self._local_repo.filectx(item, revision)
        try:
            raw_data = fctx.data()
        except error.LookupError:
            raise VersionDoesNotExist('Revision `%s` does not exist for %s in %s' % (revision, item, self.local))
        return raw_data

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

