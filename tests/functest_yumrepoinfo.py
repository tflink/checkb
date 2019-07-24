# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Functional tests for checkb/yumrepoinfo.py'''

import pytest
import mock

from checkb.ext.fedora import yumrepoinfo
from checkb import exceptions as exc

from .test_yumrepoinfo import TEST_CONF


@pytest.mark.usefixtures('setup')
class TestYumRepoInfo(object):

    @pytest.fixture
    def setup(self, tmpdir, monkeypatch):
        '''Run this before every test invocation'''
        self.conf = tmpdir.join('conf.cfg')
        self.conf.write(TEST_CONF)
        self._switch_mirror = mock.Mock()
        monkeypatch.setattr(yumrepoinfo.YumRepoInfo, '_switch_to_mirror', self._switch_mirror)
        self.repoinfo = yumrepoinfo.YumRepoInfo(filelist=[self.conf.strpath])

    def test_init_filelist(self, tmpdir):
        '''test YumRepoInfo(filelist=) with custom config files'''
        conf1 = tmpdir.join('conf1.cfg')
        conf2 = tmpdir.join('conf2.cfg')
        conf1.write('''
[DEFAULT]
baseurl = test_url
[rawhide]
a = foo''')
        conf2.write('''
[DEFAULT]
baseurl = test_url
[rawhide]
b = bar''')
        repoinfo = yumrepoinfo.YumRepoInfo(filelist=[conf1.strpath,
                                                     conf2.strpath])

        # must read conf1
        assert repoinfo.get('rawhide', 'a') == 'foo'

        # must not read conf2
        with pytest.raises(exc.CheckbConfigError):
            repoinfo.get('rawhide', 'b')

        # must not read default configs
        with pytest.raises(exc.CheckbConfigError):
            repoinfo.get('rawhide', 'tag')

    def test_init_raise(self, tmpdir):
        '''Raise an exception when configs don't exist or are empty'''
        conf1 = tmpdir.join('conf1.cfg')
        conf2 = tmpdir.join('conf2.cfg')
        conf2.write('')

        # non-existent
        with pytest.raises(exc.CheckbConfigError):
            yumrepoinfo.YumRepoInfo(filelist=[conf1.strpath])

        # empty
        with pytest.raises(exc.CheckbConfigError):
            yumrepoinfo.YumRepoInfo(filelist=[conf2.strpath])

    def test_init_altarch(self, tmpdir):
        '''Requesting alternate arch must change baseurl'''
        self.repoinfo = yumrepoinfo.YumRepoInfo(arch='i386', filelist=[self.conf.strpath])
        assert self.repoinfo.get('rawhide', 'url').startswith(
            self.repoinfo.get('DEFAULT', 'baseurl_altarch'))

        # but when primary arch is requested, baseurl must not be changed
        self.repoinfo = yumrepoinfo.YumRepoInfo(arch='x86_64', filelist=[self.conf.strpath])
        assert not self.repoinfo.get('rawhide', 'url').startswith(
            self.repoinfo.get('DEFAULT', 'baseurl_altarch'))
        assert (self.repoinfo.get('DEFAULT', 'baseurl') !=
                self.repoinfo.get('DEFAULT', 'baseurl_altarch'))

    def test_init_altarch_override(self, tmpdir):
        '''It must be possible to override alternate_arches in a repo'''
        self.repoinfo = yumrepoinfo.YumRepoInfo(arch='i386', filelist=[self.conf.strpath])
        assert not self.repoinfo.get('f21', 'url').startswith(
            self.repoinfo.get('DEFAULT', 'baseurl_altarch'))
