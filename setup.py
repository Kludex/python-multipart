#!/usr/bin/env python

import os
import re
from setuptools import setup

version_file = os.path.join('multipart', '_version.py')
with open(version_file, 'rb') as f:
    version_data = f.read().strip().decode('ascii')

version_re = re.compile(r'((?:\d+)\.(?:\d+)\.(?:\d+))')
version = version_re.search(version_data).group(0)

tests_require = [
    'pytest',
    'pytest-cov',
    'PyYAML'
]

setup(name='python-multipart',
      version=version,
      description='A streaming multipart parser for Python',
      author='Andrew Dunham',
      url='https://github.com/andrew-d/python-multipart',
      license='Apache',
      platforms='any',
      zip_safe=False,
      tests_require=tests_require,
      packages=[
          'multipart',
          'multipart.tests',
      ],
      python_requires='>=3.6',
      classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: Apache Software License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3 :: Only',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Topic :: Software Development :: Libraries :: Python Modules'
      ],
      test_suite = 'multipart.tests.suite',
     )

