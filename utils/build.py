# -*- coding: utf-8 -*-
# Copyright 2017, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Methods to help out with project building and maintenance'''

from __future__ import absolute_import
import re
import os


def find_version(path='checkb/__init__.py'):
    '''Parse out a version string from a file and return it.

    :param str path: file path containing version string
    :return: version found in the file
    :rtype: str
    :raise RuntimeError: if no version is found in the file
    '''
    here = os.path.abspath(os.path.dirname(__file__))
    filepath = os.path.abspath(os.path.join(here, '..', path))

    with open(filepath) as file_:
        data = file_.read()
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]", data, re.M)

    if version_match:
        return version_match.group(1)
    else:
        raise RuntimeError("Unable to find version string in: %s" % filepath)
