#!/usr/bin/env python
import logging
import logging.handlers
import os
import sys

DIRNAME = os.path.dirname(os.path.abspath(__file__))

def runtests(*test_args):
    if not test_args:
        test_args = ['tests']
    sys.path.insert(0, DIRNAME)
    os.environ['DJANGO_SETTINGS_MODULE'] = 'versions.tests.settings'

    log = logging.getLogger('versions')
    handler = logging.handlers.MemoryHandler(1000)
    log.addHandler(handler)
    from django.test.simple import run_tests
    failures = run_tests(test_args, verbosity=1, interactive=True)
    from versions.tests.debugging import stats
    stats.results()
    sys.exit(failures)

if __name__ == '__main__':
    runtests(*sys.argv[1:])
