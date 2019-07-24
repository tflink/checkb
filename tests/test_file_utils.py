# -*- coding: utf-8 -*-
# Copyright 2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Unit tests for checkb/file_utils.py'''

import os


def mock_download(*args, **kwargs):
    '''This mocks ``file_utils.download()``, ignores everything except ``url``
    and ``dirname`` arguments, and returns the path to the would-be created
    file.'''
    url = kwargs.get('url', args[0])
    dirname = kwargs.get('dirname', args[1])

    filename = os.path.basename(url)
    dest = os.path.join(dirname, filename)

    return dest
