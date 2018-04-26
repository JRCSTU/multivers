#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Setup script *polyvers-cmd*."""

import sys

from setuptools import setup, find_packages

from pvlib.polyversion import polyversion


MIN_PYTHON = (3, 6)
if sys.version_info < MIN_PYTHON:
    sys.exit("Sorry, Python >= %s is required, found: %s" %
             ('.'.join(str(i) for i in MIN_PYTHON), str(sys.version_info)))
with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

## Remove 1st header-mark line or else,
#  README.rst gets invalid header levels.
history = '\n'.join(history.split('\n')[1:])


requirements = [
    'boltons',                  # for IndexSet
    'toolz',
    'rainbow_logging_handler',
    'ruamel.yaml',              # for logconf
    'ipython_genutils',         # by vendorized `traitlets`
    'spectate',                 # by vendorized `traitlets`
    'ruamel.yaml>=0.15.37',     # fix PY3.7 ruamel/yaml#187
    "contextvars; python_version<'3.7'",  # for yaml-exporting cmdlets
    'packaging==17.1',
]

test_requirements = [
    'pytest >= 3.5.0',  # caplog.clear() fixed (pytest-dev/pytest#3297)
    'pytest-runner',
    'pytest-cov',
    'flake8',
    'flake8-builtins',
    'flake8-mutable',
    #'mypy',
]
PROJECT = 'polyvers'
setup(
    name=PROJECT,
    version=polyversion(PROJECT, '0.0.0'),
    description="Bump sub-project PEP-440 versions in Git monorepos independently.",
    long_description=readme + '\n\n' + history,
    author="Kostis Anagnostopoulos",
    author_email='ankostis@gmail.com',
    url='https://github.com/jrcstu/polyvers',
    download_url='https://pypi.org/project/polyvers/',
    project_urls={
        'Documentation': 'http://polyvers.readthedocs.io/',
        'Source': 'https://github.com/jrcstu/polyvers',
        'Tracker': 'https://github.com/jrcstu/polyvers/issues',
    },
    package_dir={'': 'pvcmd'},
    packages=find_packages('pvcmd', exclude=['tests*']),
    include_package_data=True,
    setup_requires=['polyversion'],
    install_requires=requirements,
    license='EUPL 1.2',
    zip_safe=True,
    platforms=['any'],
    keywords="version-management configuration-management versioning "
             "git monorepo tool library".split(),
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: European Union Public Licence 1.1 (EUPL 1.1)',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    test_suite='tests',
    python_requires='>=3.6',
    tests_require=test_requirements,
    extras_require={
        'test': test_requirements,
        'test:python_version>="3"': ['mypy']
    },
    entry_points={
        'console_scripts': [
            '%(p)s = %(p)s.__main__:main' % {'p': PROJECT}]},
)
