import uuid
import profile
import pstats
import os

class Stats(object):
    def __init__(self):
        self.files = []
        if not os.path.exists('profiling_data/'):
            os.makedirs('profiling_data/')

    def profile(self, func):
        def _(*args, **kwargs):
            filename = 'profiling_data/%s-%s.stats' % (func.__name__, uuid.uuid4())
            profile.runctx('func(*args, **kwargs)', {}, {'func': func, 'args': args, 'kwargs': kwargs}, filename=filename)
            self.files.append(filename)
        return _

    def results(self):
        if self.files:
            _stats = pstats.Stats(self.files[0])
            os.unlink(stat_file)
            for stat_file in self.files[1:]:
                _stats.add(stat_file)
                os.unlink(stat_file)
            _stats.sort_stats('time') #cumulative
            _stats.print_stats()
        else:
            print 'No stats were collected.'

stats = Stats()
