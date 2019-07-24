# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Unit tests for checkb.ext.fedora.rpm_utils'''

import pytest
import subprocess

from checkb.ext.fedora.rpm_utils import (cmpNEVR, get_dist_tag, install,
                                         rpmformat)
from checkb import exceptions as exc
from checkb import os_utils

import mock


class TestRpmformat:

    def test_nvra(self):
        '''NVRA as input param'''
        rpmstr = 'foo-1.2-3.fc20.x86_64'
        assert rpmformat(rpmstr, 'nevra', True) == 'foo-1.2-3.fc20.x86_64'
        assert rpmformat(rpmstr, 'nevr', True) == 'foo-1.2-3.fc20'
        assert rpmformat(rpmstr, 'nvra', True) == 'foo-1.2-3.fc20.x86_64'
        assert rpmformat(rpmstr, 'nvr', True) == 'foo-1.2-3.fc20'
        assert rpmformat(rpmstr, 'n', True) == 'foo'
        assert rpmformat(rpmstr, 'e', True) == 0
        assert rpmformat(rpmstr, 'v', True) == '1.2'
        assert rpmformat(rpmstr, 'r', True) == '3.fc20'
        assert rpmformat(rpmstr, 'a', True) == 'x86_64'

    def test_nevra(self):
        '''NEVRA as input param'''
        rpmstr = 'foo-4:1.2-3.fc20.x86_64'
        assert rpmformat(rpmstr, 'nevra', True) == 'foo-4:1.2-3.fc20.x86_64'
        assert rpmformat(rpmstr, 'nevr', True) == 'foo-4:1.2-3.fc20'
        assert rpmformat(rpmstr, 'nvra', True) == 'foo-1.2-3.fc20.x86_64'
        assert rpmformat(rpmstr, 'nvr', True) == 'foo-1.2-3.fc20'
        assert rpmformat(rpmstr, 'n', True) == 'foo'
        assert rpmformat(rpmstr, 'e', True) == 4
        assert rpmformat(rpmstr, 'v', True) == '1.2'
        assert rpmformat(rpmstr, 'r', True) == '3.fc20'
        assert rpmformat(rpmstr, 'a', True) == 'x86_64'

    def test_nevra_epoch_zero(self):
        '''Zero epoch is valid and it should be treated as no epoch'''
        rpmstr = 'foo-0:1.2-3.fc20.x86_64'
        assert rpmformat(rpmstr, 'nevra', True) == 'foo-1.2-3.fc20.x86_64'
        assert rpmformat(rpmstr, 'nevr', True) == 'foo-1.2-3.fc20'
        assert rpmformat(rpmstr, 'nvra', True) == 'foo-1.2-3.fc20.x86_64'
        assert rpmformat(rpmstr, 'nvr', True) == 'foo-1.2-3.fc20'
        assert rpmformat(rpmstr, 'n', True) == 'foo'
        assert rpmformat(rpmstr, 'e', True) == 0
        assert rpmformat(rpmstr, 'v', True) == '1.2'
        assert rpmformat(rpmstr, 'r', True) == '3.fc20'
        assert rpmformat(rpmstr, 'a', True) == 'x86_64'

    def test_nvr(self):
        '''NVR as input param'''
        rpmstr = 'foo-1.2-3.fc20'
        assert (rpmformat(rpmstr, 'nvr') == 'foo-1.2-3.fc20' ==
                rpmformat(rpmstr, 'nevr'))
        # noarch is added when arch requested
        assert (rpmformat(rpmstr, 'nvra') == 'foo-1.2-3.fc20.noarch' ==
                rpmformat(rpmstr, 'nevra'))
        assert rpmformat(rpmstr, 'e') == 0

    def test_nevr(self):
        '''NEVR as input param'''
        rpmstr = 'foo-1:1.2-3.fc20'
        assert rpmformat(rpmstr, 'nevr') == 'foo-1:1.2-3.fc20'
        # noarch is added when arch requested
        assert rpmformat(rpmstr, 'nevra') == 'foo-1:1.2-3.fc20.noarch'
        assert rpmformat(rpmstr, 'e') == 1

    def test_caps(self):
        '''Letter case should not matter in fmt'''
        assert rpmformat('foo-1.2-3.fc20', 'NVR') == 'foo-1.2-3.fc20'

    def test_raise(self):
        '''Test incorrect fmt'''
        with pytest.raises(exc.CheckbValueError):
            rpmformat('foo-1.2-3.fc20', 'x')

        with pytest.raises(exc.CheckbValueError):
            rpmformat('foo-1.2-3.fc20', 'envra')

        with pytest.raises(exc.CheckbValueError):
            rpmformat('foo-1.2-3.fc20', 'n-v-r')


class TestCmpNEVR(object):

    def test_no_epoch(self):
        '''Both params without epoch'''
        assert cmpNEVR('foo-1.2-3.fc20', 'foo-1.2-2.fc20') == 1
        assert cmpNEVR('foo-1.2-3.fc20', 'foo-1.2-3.fc20') == 0
        assert cmpNEVR('foo-1.2-3.fc20', 'foo-1.2-4.fc20') == -1

        assert cmpNEVR('foo-1.2-3.fc20', 'foo-1.1-4.fc20') == 1
        assert cmpNEVR('foo-1.2-3.fc20', 'foo-2.1-1.fc20') == -1
        assert cmpNEVR('foo-1.2-3.fc20', 'foo-1.2-3.fc19') == 1

    def test_epoch(self):
        '''Both params with epoch'''
        assert cmpNEVR('foo-1:1.2-3.fc20', 'foo-1:1.2-2.fc20') == 1
        assert cmpNEVR('foo-1:1.2-3.fc20', 'foo-1:1.2-3.fc20') == 0
        assert cmpNEVR('foo-0:1.2-3.fc20', 'foo-0:1.2-3.fc20') == 0
        assert cmpNEVR('foo-3:1.2-3.fc20', 'foo-3:1.2-4.fc20') == -1

        assert cmpNEVR('foo-2:1.2-3.fc20', 'foo-2:1.1-4.fc20') == 1
        assert cmpNEVR('foo-2:1.2-3.fc20', 'foo-2:2.1-1.fc20') == -1
        assert cmpNEVR('foo-2:1.2-3.fc20', 'foo-2:1.2-3.fc19') == 1

        assert cmpNEVR('foo-1:1.2-3.fc20', 'foo-2:1.2-3.fc20') == -1
        assert cmpNEVR('foo-1:1.2-3.fc20', 'foo-0:1.2-3.fc20') == 1
        assert cmpNEVR('foo-1:1.2-3.fc20', 'foo-0:2.2-3.fc20') == 1

    def test_some_epoch(self):
        '''One param with epoch'''
        assert cmpNEVR('foo-1:1.2-3.fc20', 'foo-1.2-3.fc20') == 1
        assert cmpNEVR('foo-1:1.2-3.fc20', 'foo-2.2-3.fc20') == 1
        assert cmpNEVR('foo-0:1.2-3.fc20', 'foo-1.2-3.fc20') == 0
        assert cmpNEVR('foo-1.2-3.fc20', 'foo-2:0.1-1.fc19') == -1

    def test_raise(self):
        '''Invalid input param'''
        with pytest.raises(exc.CheckbValueError):
            cmpNEVR('foo-1.2-3.fc20', 'bar-1.2-3.fc20')


@pytest.mark.usefixtures('setup')
class TestInstall(object):
    '''Test rpm_utils.install()'''

    @pytest.fixture
    def setup(self, monkeypatch):
        self.mock_is_root = mock.Mock(return_value=True)
        monkeypatch.setattr(os_utils, 'is_root', self.mock_is_root)
        self.mock_has_sudo = mock.Mock(return_value=True)
        monkeypatch.setattr(os_utils, 'has_sudo', self.mock_has_sudo)

        self.mock_check_output = mock.Mock(return_value='')
        monkeypatch.setattr(subprocess, 'check_output', self.mock_check_output)
        self.err = subprocess.CalledProcessError(1, 'cmd', output='')

    def test_install_ok(self):
        install(['foo'])

    def test_install_fails(self):
        self.mock_check_output.side_effect = self.err
        with pytest.raises(exc.CheckbError) as excinfo:
            install(['foo'])

        # direct comparison here, because isinstance() would also accept subclasses we throw for
        # different issues (missing permissions)
        assert type(excinfo.value) is exc.CheckbError

    def test_no_permissions(self):
        self.mock_is_root.return_value = False
        self.mock_has_sudo.return_value = False

        with pytest.raises(exc.CheckbPermissionError):
            install(['foo'])

    def test_add_sudo(self):
        self.mock_is_root.return_value = False
        install(['foo'])
        assert self.mock_check_output.call_args[0][0].index('sudo') == 0

    def test_dont_add_sudo(self):
        install(['foo'])
        assert 'sudo' not in self.mock_check_output.call_args[0][0]

    def test_no_pkgs(self):
        install([])
        assert self.mock_check_output.call_count == 0

    def test_special_args(self):
        '''Make sure args like 'rpmlint > 1.0' are passed in correctly'''
        pkgs = ['foo', 'bar >= 1.0', '@group']
        install(pkgs)

        call_args = self.mock_check_output.call_args[0][0]
        assert all([pkg in call_args for pkg in pkgs])


class TestGetDistTag(object):
    def test_nvrs(self):
        assert get_dist_tag('foo-1.2-3.fc20') == 'fc20'
        assert get_dist_tag('foo-1.2-3.fc20.1') == 'fc20'
        assert get_dist_tag('foo-1.2-3.fc22hashgit.fc20') == 'fc20'
        assert get_dist_tag('foo-1.2-3.fc22hashgit.fc20.1') == 'fc20'

    def test_unsupported_dist_tag(self):
        with pytest.raises(exc.CheckbValueError):
            get_dist_tag('foo-1.2-3.el7')
