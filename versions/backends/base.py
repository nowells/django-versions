class BaseRepository(object):
    def __init__(self, key, local=None, remote=None):
        self.key = key
        self.local = local
        self.remote = remote

    def commit(self, items):
        raise NotImplementedError

    def versions(self, item):
        raise NotImplementedError

    def version(self, item, rev=None):
        raise NotImplementedError
