import os

DIRNAME = os.path.dirname(os.path.abspath(__file__))

DEBUG = True
DATABASE_ENGINE='sqlite3'
DATABASE_NAME = os.path.join(DIRNAME, 'versions.db')
TEST_DATABASE_NAME = os.path.join(DIRNAME, 'test-versions.db')
INSTALLED_APPS=(
    'django.contrib.contenttypes',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.sessions',
    'versions',
    'versions.tests',
    )
VERSIONS_REPOSITORY_ROOT = os.path.join(DIRNAME, '.repositories')
TEMPLATE_LOADERS = (
    'django.template.loaders.filesystem.load_template_source',
    'django.template.loaders.app_directories.load_template_source',
    'django.template.loaders.eggs.load_template_source',
    )
ROOT_URLCONF = 'versions.tests.urls'
