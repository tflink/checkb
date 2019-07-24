# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Unit tests for checkb/arch_utils.py'''

import os
from checkb.arch_utils import basearch


class TestBasearch:

    def test_basearch_i386(self):
        '''i386-like archs'''
        assert basearch('i386') == 'i386'
        assert basearch('i486') == 'i386'
        assert basearch('i586') == 'i386'
        assert basearch('i686') == 'i386'

    def test_basearch_x86_64(self):
        '''x86_64 arch'''
        assert basearch('x86_64') == 'x86_64'

    def test_basearch_local(self):
        '''When no arch specified, local arch should be returned'''
        # let's say we're satisfied if /something/ is returned. Otherwise we
        # would have to copy most of the method's code in order to check it :-)
        assert basearch() == basearch(os.uname()[4])

    def test_basearch_unknown(self):
        '''Unknown arch is just returned'''
        assert basearch('some_arch') == 'some_arch'
