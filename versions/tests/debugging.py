import uuid
import profile
import pstats
import os

class Stats(object):
    def profile(self, func):
        def _(*args, **kwargs):
            filename = '%s-%s.stats' % (func.__name__, uuid.uuid4())
            profile.runctx('func(*args, **kwargs)', {}, {'func': func, 'args': args, 'kwargs': kwargs}, filename=filename)
            if not hasattr(self, '_stats'):
                self._stats = pstats.Stats(filename)
            else:
                self._stats.add(filename)
            os.unlink(filename)
        return _

    def results(self):
        if hasattr(self, '_stats'):
            #self._stats.strip_dirs()
            self._stats.sort_stats('cumulative')
            self._stats.print_stats()
        else:
            print 'No stats were collected.'

stats = Stats()
