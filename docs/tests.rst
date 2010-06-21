Running the test suite
======================

The ``versions.tests`` package is set up as a project which holds a test
settings module and defines models for use in testing Versions. You can run
the tests from the command-line using the ``django-admin.py`` script,
specifying that the test settings module should be used::

    PYTHONPATH=.:$PYTHONPATH django-admin.py test --settings=versions.tests.settings tests

Or if you forget that command, you can always just run the ``run_tests`` command located in the bin directory::

    ./bin/run_tests
