import os

DIRNAME = os.path.abspath(os.path.dirname(__file__))

DEBUG = True

DATABASE_ENGINE = 'sqlite3'
DATABASE_NAME = os.path.join(DIRNAME, 'versions.db')

INSTALLED_APPS = (
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'versions',
    'versions.tests',
    )

VERSIONS_REPOSITORY_ROOT = os.path.join(DIRNAME, '.repositories')
