# -*- coding: utf-8 -*-
# Copyright 2018, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Functional tests for content in data/ directory'''

import pytest
import os
import subprocess

from checkb import config


@pytest.mark.usefixtures('setup')
class TestAnsible():
    '''Test contents of data/ansible directory'''

    @pytest.fixture
    def setup(self, tmpdir, monkeypatch):
        '''Run this before every test invocation'''
        self.data_dir = config.get_config()._data_dir
        self.ansible_dir = os.path.join(self.data_dir, 'ansible')
        self.runner_file = 'runner.yml'

    def test_runner_syntax(self):
        '''Syntax check for runner.yml and tasks_*.yml'''
        cmd = ['ansible-playbook', '--syntax-check', self.runner_file]
        # use cwd so that our ansible.cfg gets used
        subprocess.check_call(cmd, cwd=self.ansible_dir)
