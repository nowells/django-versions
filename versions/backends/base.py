from django.contrib.auth import AnonymousUser
from django.contrib.auth.models import User

class Repository(object):
    def __init__(self, local=None, remote=None):
        self.local = local
        self.remote = remote
        self.reset()
        self.create()

    def reset(self):
        self.user = None
        self.message = None

    def create(self):
        raise NotImplementedError

    def commit(self, items):
        raise NotImplementedError

    def revisions(self, item):
        raise NotImplementedError

    def version(self, item, revision=None):
        raise NotImplementedError

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


