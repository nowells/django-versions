#!/usr/bin/env python

import sys
from distutils.core import setup
import os

version = '0.1'

setup(
    name='django-versions',
    version=version,
    description="A django application to enable versioning of Django models.",
    long_description=open('README.rst', 'r').read(),
    author='Nowell Strite',
    author_email='nowell@strite.org',
    url='http://github.com/nowells/django-versions/',
    packages=['versions'],
    license='MIT',
    classifiers=[
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
    )
