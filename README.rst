django-versions
###############

ALPHA
=====
This project's development is still in **ALPHA**. There are many features not yet implemented that are in the queue.

Overview
========

``django-versions`` allows you to version the data stored in django models seamlessly. To get started all you need to do is to set ``VERSIONS_REPOSITORY_ROOT`` variable in your settings to specify where you would like your versioned data to be stored, then just subclass your Model from ``VersionsModel`` and start saving data::

    from django.db import models
    from versions.models import VersionsModel

    class MyModel(VersionsModel):
        text = models.TextField()

Installation
============

Dependencies
------------

* Mercurial >= 1.5.2
* Django == 1.1

Installing django-versions
--------------------------

If your are installing from source, you just need to run the following command from the base of the ``django-versions`` source tree::

    python setup.py install

If you want to install the package without checking out the source you should run::

    pip install http://github.com/nowells/django-versions/tarball/v0.1.0

    # OR if you don't have pip installed (you should definitely check out pip)
    easy_install http://github.com/nowells/django-versions/tarball/v0.1.0

For the time being, we need to patch Django to allow us to gain access to the related model from Manager classes. There is a patch included at the root of the source tree ``django.patch`` that includes the required changes. To patch django, go to the root of your checkout of django 1.1.X and run::

    patch -p0 < /path/to/django-versions/django.patch

Add ``VERSIONS_REPOSITORY_ROOT`` to your settings file, pointing to the location where you would like ``django-versions`` to create and store your model history::

    VERSIONS_REPOSITORY_ROOT = '/path/to/my/projects/model/history'

Optionally, install ``VersionsMiddleware`` to allow for grouping all model changes within a request into one commit::

    MIDDLEWARE_CLASSES = (
        ...
        'versions.middleware.VersionsMiddleware',
        ...
        )
