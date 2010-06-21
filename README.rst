django-versions
###############

Overview
========

django-versions allows you to version the data stored in django models seamlessly. To get started all you need to do is to set ``VERSIONS_REPOSITORY_ROOT`` variable in your settings to specify where you would like your versioned data to be stored, then just subclass your Model from ``VersionsModel`` and start saving data.:

    from django.db import models
    from versions import VersionsModel

    class MyModel(VersionsModel):
        text = models.TextField()

Installation
============

Dependencies
------------

* Mercurial >= 1.5.2

Installing django-versions
--------------------------

Install into your python path using pip or easy_install::

    pip install django-versions
    easy_install django-versions

Add ``VERSIONS_REPOSITORY_ROOT`` to your settings file, pointing to the location where you would like django-versions to create and store your model history.:

    VERSIONS_REPOSITORY_ROOT = '/path/to/my/projects/model/history'

Optionally, install ``VersionsMiddleware`` to allow for grouping all model changes within a request into one commit::

    MIDDLEWARE_CLASSES = (
        ...
        'versions.middleware.VersionsMiddleware',
        ...
        )
