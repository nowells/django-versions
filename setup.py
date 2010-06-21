#!/usr/bin/env python

import os
import sys
from setuptools import setup

from versions import VERSION

f = open(os.path.join(os.path.dirname(__file__), 'README.rst'))
README = f.read()
f.close()

setup(
    name='django-versions',
    version='.'.join(map(str, VERSION)),
    description="A django application to enable versioning of data stored in Django models.",
    long_description=README,
    author='Nowell Strite',
    author_email='nowell@strite.org',
    url='http://github.com/nowells/django-versions/',
    packages=['versions', 'versions.tests'],
    license='MIT',
    install_requires=['mercurial>=1.5.2'],
    zip_safe=False,
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Utilities',
        'Natural Language :: English',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: POSIX :: Linux',
        'Operating System :: Unix',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.5',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Topic :: Software Development :: Version Control',
        'Topic :: Utilities',
        ],
    test_suite='runtests.runtests',
    )
