#!/usr/bin/env python
import os
import sys

from django.conf import settings

DIRNAME = os.path.dirname(os.path.abspath(__file__))

if not settings.configured:
    settings.configure(
        DATABASE_ENGINE='sqlite3',
        DATABASE_NAME = os.path.join(DIRNAME, 'versions.db'),
        INSTALLED_APPS=[
            'django.contrib.contenttypes',
            'django.contrib.auth',
            'versions.tests',
            ],
        VERSIONS_REPOSITORY_ROOT = os.path.join(DIRNAME, '.repositories'),
        )

from django.test.simple import run_tests

def runtests(*test_args):
    if not test_args:
        test_args = ['tests']
    sys.path.insert(0, DIRNAME)
    failures = run_tests(test_args, verbosity=1, interactive=True)
    sys.exit(failures)

if __name__ == '__main__':
    runtests(*sys.argv[1:])
