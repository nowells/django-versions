#!/usr/bin/env python
import os
import sys

DIRNAME = os.path.dirname(os.path.abspath(__file__))

def runtests(*test_args):
    if not test_args:
        test_args = ['tests']
    sys.path.insert(0, DIRNAME)
    os.environ['DJANGO_SETTINGS_MODULE'] = 'versions.tests.settings'

    from django.test.simple import run_tests
    failures = run_tests(test_args, verbosity=1, interactive=True)
    sys.exit(failures)

if __name__ == '__main__':
    runtests(*sys.argv[1:])
