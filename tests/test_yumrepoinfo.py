# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Unit tests for checkb/yumrepoinfo.py'''

import pytest
import mock
from io import StringIO
import sys

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

from checkb.ext.fedora import yumrepoinfo
from checkb import exceptions as exc


TEST_CONF=u'''\
[DEFAULT]
baseurl = http://download.fedoraproject.org/pub/fedora/linux
baseurl_altarch = http://download.fedoraproject.org/pub/fedora-secondary
goldurl = %(baseurl)s/releases/%(path)s/Everything/%(arch)s/os
updatesurl = %(baseurl)s/updates/%(path)s/%(arch)s
rawhideurl = %(baseurl)s/%(path)s/%(arch)s/os
primary_arches = armhfp, x86_64
alternate_arches = i386
parent =
tag =
release_status =

[rawhide]
path = development/rawhide
url = %(rawhideurl)s
tag = f22
release_status = rawhide

[f21]
url = %(rawhideurl)s
path = development/21
release_status = Branched
alternate_arches =
tag = f21

[f20]
url = %(goldurl)s
path = 20
release_status = STABLE
tag = f20

[f20-updates]
url = %(updatesurl)s
path = 20
parent = f20
primary_arches = x86_64
tag = f20-updates

[f20-updates-testing]
url = %(updatesurl)s
path = testing/20
parent = f20-updates
tag = f20-updates-testing

[f15]
url = not_really_an_url
path = 15
release_status = obsolete
tag = f15
'''

@pytest.mark.usefixtures('setup')
class TestYumRepoInfo(object):

    @pytest.fixture
    def setup(self, monkeypatch):
        '''Run this before every test invocation'''
        monkeypatch.setattr(yumrepoinfo.YumRepoInfo, '_switch_to_mirror', mock.Mock())
        # create YumRepoInfo initialized with TEST_CONF
        self.repoinfo = yumrepoinfo.YumRepoInfo(filelist=[])
        if (sys.version_info >= (3, 2)):
            self.repoinfo.parser.read_file(StringIO(TEST_CONF))
        else:
            self.repoinfo.parser.readfp(StringIO(TEST_CONF))

    @pytest.fixture
    def disable_disk_loading(self, monkeypatch):
        '''Patch ConfigParser not to load from disk.'''

        # instead of reading from disk, just return the input parameter
        monkeypatch.setattr(configparser.RawConfigParser, 'read',
                            lambda self, cfg: cfg)

    @pytest.fixture
    def clean_singleton(self, monkeypatch):
        '''Replace singleton container with an empty dict'''
        monkeypatch.setattr(yumrepoinfo, '_yumrepoinfo', {})

    def test_init_arch(self, disable_disk_loading):
        '''Test YumRepoInfo(arch=)'''
        repoinfo = yumrepoinfo.YumRepoInfo(arch='x86_64', filelist=[])
        if (sys.version_info >= (3, 2)):
            repoinfo.parser.read_file(StringIO(TEST_CONF))
        else:
            repoinfo.parser.readfp(StringIO(TEST_CONF))
        assert '/x86_64/' in repoinfo.get('rawhide', 'url')

    def test_init_basearch(self, disable_disk_loading):
        '''i686 should be converted to i386'''
        repoinfo = yumrepoinfo.YumRepoInfo(arch='i686', filelist=[])
        if (sys.version_info >= (3, 2)):
            repoinfo.parser.read_file(StringIO(TEST_CONF))
        else:
            repoinfo.parser.readfp(StringIO(TEST_CONF))
        assert '/i386/' in repoinfo.get('rawhide', 'url')

    def test_init_empty_filelist(self, monkeypatch):
        '''YumRepoInfo(filelist=[]) should not load anything from disk'''
        # make sure the disk is not read
        def _raise_alarm(x):
            assert False, 'This must not be called'
        monkeypatch.setattr(configparser.RawConfigParser, 'read', _raise_alarm)

        repoinfo = yumrepoinfo.YumRepoInfo(filelist=[])
        assert not repoinfo.repos()

    def test_repos(self):
        '''repos() should return all known repo names'''
        assert self.repoinfo.repos() == ['rawhide', 'f21', 'f20', 'f20-updates',
                                         'f20-updates-testing', 'f15']

    def test_releases(self):
        '''releases() should return only stable releases repo names'''
        assert self.repoinfo.releases() == ['f20']

    def test_branched(self):
        '''branched() should return branched release repo name'''
        assert self.repoinfo.branched() == 'f21'

    def test_arches(self):
        '''arches() should return what's defined in a section'''
        assert sorted(self.repoinfo.arches('DEFAULT')) == sorted(['i386', 'x86_64', 'armhfp'])
        assert sorted(self.repoinfo.arches('rawhide')) == sorted(['i386', 'x86_64', 'armhfp'])
        assert sorted(self.repoinfo.arches('f21')) == sorted(['x86_64', 'armhfp'])
        assert sorted(self.repoinfo.arches('f20-updates')) == sorted(['x86_64', 'i386'])

    def test_get(self):
        '''get() simply returns a key'''
        assert self.repoinfo.get('rawhide', 'release_status') == 'rawhide'
        assert self.repoinfo.get('DEFAULT', 'parent') == ''

    def test_get_raise(self):
        '''get() should raise an error when the key doesn't exist'''
        with pytest.raises(exc.CheckbConfigError):
            self.repoinfo.get('rawhide', 'non-existent key')

        with pytest.raises(exc.CheckbConfigError):
            self.repoinfo.get('non-existent repo', 'tag')

    def test_repo(self):
        '''repo() returns a repo dict'''
        rawhide = self.repoinfo.repo('rawhide')
        assert rawhide['name'] == 'rawhide'
        assert rawhide['tag'] == 'f22'
        assert set(rawhide.keys()).issuperset(
            set(('arches', 'parent', 'tag', 'url', 'path', 'name'))
        )

    def test_repo_by_tag(self):
        '''repo_by_tag() must work based on tags, not section names'''
        f20up = self.repoinfo.repo_by_tag('f20-updates')
        assert f20up['name'] == f20up['tag'] == 'f20-updates'

        f21 = self.repoinfo.repo_by_tag('f22')
        assert f21['tag'] == 'f22'
        assert f21['name'] == 'rawhide'

        assert self.repoinfo.repo_by_tag('foobar') is None

    def test_top_parent(self):
        '''top_parent() must travel the hierarchy'''
        assert self.repoinfo.top_parent('rawhide') == 'rawhide'
        assert self.repoinfo.top_parent('f20-updates') == 'f20'
        assert self.repoinfo.top_parent('f20-updates-testing') == 'f20'

    def test_top_parent_raise(self):
        '''top_parent() must detect an infinite parent cycle'''
        cfg = u'''\
[repo1]
parent = repo2
[repo2]
parent = repo1
'''
        repoinfo = yumrepoinfo.YumRepoInfo(filelist=[])
        if (sys.version_info >= (3, 2)):
            repoinfo.parser.read_file(StringIO(cfg))
        else:
            repoinfo.parser.readfp(StringIO(cfg))

        with pytest.raises(exc.CheckbConfigError):
            repoinfo.top_parent('repo1')

    def test_repo_release_status(self):
        assert self.repoinfo.release_status('f21') == 'branched'
        assert self.repoinfo.release_status('f20') == 'stable'
        assert self.repoinfo.release_status('f20-updates-testing') == 'stable'
        assert self.repoinfo.release_status('f15') == 'obsolete'

    def test_get_yumrepoinfo(self, clean_singleton):
        '''get_yumrepoinfo must work as a singleton'''

        repoinfo = yumrepoinfo.get_yumrepoinfo()
        # two calls with same arch must return the same instance
        assert repoinfo is yumrepoinfo.get_yumrepoinfo()
        # there should be a record in the singleton container
        assert len(yumrepoinfo._yumrepoinfo.keys()) > 0

        # the same must work for basearch conversion
        repoinfo_i686 = yumrepoinfo.get_yumrepoinfo(arch='i686')
        repoinfo_i386 = yumrepoinfo.get_yumrepoinfo(arch='i386')
        assert repoinfo_i686 is repoinfo_i386
        assert 'i386' in yumrepoinfo._yumrepoinfo
        assert 'i686' not in yumrepoinfo._yumrepoinfo
