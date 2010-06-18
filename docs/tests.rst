Running the test suite
======================

The ``versions.tests`` package is set up as a project which holds a test
settings module and defines models for use in testing Versions. You can run
the tests from the command-line using the ``django-admin.py`` script,
specifying that the test settings module should be used::

   django-admin.py test --settings=versions.tests.settings
