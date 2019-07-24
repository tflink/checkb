# -*- coding: utf-8 -*-
# Copyright 2016, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Unit tests for checkb.os_utils'''

import os
import subprocess
import mock
import pytest

from checkb.os_utils import is_root, has_sudo, popen_rt
import checkb.exceptions as exc


class TestIsRoot(object):
    '''Test os_utils.is_root()'''

    def test_root(self, monkeypatch):
        mock_geteuid = mock.Mock(return_value=0)
        monkeypatch.setattr(os, 'geteuid', mock_geteuid)
        assert is_root()

    def test_not_root(self, monkeypatch):
        mock_geteuid = mock.Mock(return_value=1000)
        monkeypatch.setattr(os, 'geteuid', mock_geteuid)
        assert not is_root()


class TestHasSudo(object):
    '''Test os_utils.has_sudo()'''

    def test_sudo(self, monkeypatch):
        mock_check_output = mock.Mock()
        monkeypatch.setattr(subprocess, 'check_output', mock_check_output)
        assert has_sudo()

    def test_no_sudo(self, monkeypatch):
        err = subprocess.CalledProcessError(1, 'cmd', output='')
        mock_check_output = mock.Mock(side_effect=err)
        monkeypatch.setattr(subprocess, 'check_output', mock_check_output)
        assert not has_sudo()


class TestPopenRT(object):
    '''Test os_utils.popen_rt()'''

    def test_raise_stdout(self):
        with pytest.raises(exc.CheckbValueError):
            popen_rt(['false'], stdout=None)
