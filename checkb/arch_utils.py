# -*- coding: utf-8 -*-
# Copyright 2009-2016, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

from __future__ import absolute_import
import os
import itertools


class Arches(object):
    '''
    Helper class for working with supported architectures inside checkb
    '''

    #: a mapping from base arches to concrete binary arches
    binary = {
        'aarch64': ['aarch64'],
        'armhfp':  ['armhfp', 'armv7hl'],
        'i386':    ['i386', 'i486', 'i586', 'i686'],
        'ppc64':   ['ppc64'],
        'ppc64le': ['ppc64le'],
        's390x':   ['s390x'],
        'x86_64':  ['x86_64'],
    }

    #: base architectures
    base = binary.keys()

    #: meta arches
    meta = ['noarch', 'src']

    #: all known architectures
    known = sorted(set(list(binary.keys()) + list(itertools.chain(*binary.values())) + meta))


def basearch(arch=None):
    '''
    This returns the 'base' architecture identifier for a specified architecture
    (e.g. ``i386`` for ``i[3-6]86``), to be used by YUM etc.

    :param str arch: an architecture to be converted to a basearch. If ``None``,
                     then the arch of the current machine is used.
    :return: basearch, or ``arch`` if no basearch was found for it
    :rtype: str
    '''
    if arch is None:
        arch = os.uname()[4]

    for base, binary in Arches.binary.items():
        if arch == base or arch in binary:
            return base

    return arch
