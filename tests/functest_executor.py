# -*- coding: utf-8 -*-
# Copyright 2018, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Functional tests for checkb/executor.py'''

import pytest
import mock
import signal

from checkb import executor
import checkb.exceptions as exc
from checkb import config

PLAYBOOK='''
- hosts: localhost
  # this saves a lot of time when running in mock (without network)
  gather_facts: no
  vars:
    checkb_generic_task: true
  tasks:
    - debug:
        msg: This is a sample debug printout
'''


@pytest.mark.usefixtures('setup')
class TestExecutor():

    @pytest.fixture
    def setup(self, tmpdir, monkeypatch):
        '''Run this before every test invocation'''
        self.artifactsdir = tmpdir.mkdir('artifacts')
        self.taskdir = tmpdir.mkdir('taskdir')
        self.client_taskdir = tmpdir.mkdir('client_taskdir')
        self.arg_data = {
            'artifactsdir': self.artifactsdir.strpath,
            'taskdir': self.taskdir.strpath,
            'item': 'htop-2.0.2-4.fc27',
            'type': 'koji_build',
            'arch': 'noarch',
            'debug': False,
            'local': True,
            'libvirt': False,
            'ssh': False,
            'ssh_privkey': None,
        }
        self.playbook_name = 'tests.yml'
        self.playbook = self.taskdir.join(self.playbook_name)
        self.playbook.write(PLAYBOOK)
        self.ipaddr = '127.0.0.1'
        self.executor = executor.Executor(self.arg_data)
        self.playbook_vars = self.executor._create_playbook_vars(
            self.playbook_name)

        monkeypatch.setattr(config, '_config', None)
        self.conf = config.get_config()
        self.conf.client_taskdir = self.client_taskdir.strpath

    def test_syntax_check_valid(self):
        '''Should not raise if playbook has valid syntax'''
        self.executor._check_playbook_syntax(self.playbook.strpath)

    def test_syntax_check_invalid(self):
        '''Should raise if playbook has invalid syntax'''
        self.playbook.write("This surely isn't a valid Ansible playbook")
        with pytest.raises(exc.CheckbPlaybookError):
            self.executor._check_playbook_syntax(self.playbook.strpath)

    def test_run_playbook_simple(self, monkeypatch):
        '''Execute a very simple playbook whether everything works'''
        # don't override Ctrl+C during testing
        mock_signal = mock.Mock()
        monkeypatch.setattr(signal, 'signal', mock_signal)
        # it's non-default, but we can't run the test suite as root
        self.playbook_vars['become_root'] = False

        output = self.executor._run_playbook(self.playbook_name,
            self.ipaddr, self.playbook_vars)
        # FIXME: We currently have no idea whether the test playbook passed
        # or failed, because we ignore the inner playbook's exit status. So
        # we can't really verify here whether everything worked ok.
        # To work around this, we grep for known lines in stdout. The warning
        # printout about failed task must be skipped.
        lines = output.splitlines()
        matched = [line for line in lines
            if line.startswith('TASK [Warn about failed task]')]
        assert len(matched) == 1
        warn_task_line = lines.index(matched[0])
        assert 'skipping' in lines[warn_task_line + 1]

    def test_get_vault_secrets(self, monkeypatch):
        class MockRequests(object):
            def __init__(self, retval):
                self.ok = True
                self.retval = retval
                self.exceptions = mock.Mock()
            def get(self, *args, **kwargs):
                return self
            def json(self, *args, **kwargs):
                return self.retval

        self.conf.vault_enabled = True

        mock_git_origin_url = mock.Mock(return_value='fake://repo.git')
        monkeypatch.setattr(executor.resultsdb_directive, 'git_origin_url', mock_git_origin_url)

        mock_requests = MockRequests({'data': [
                {
                  'description': 'dat description',
                  'secrets': 'dem secrets',
                  'uuid': 'dat uuid',
                }
             ]})
        mock_session = mock.Mock(return_value=mock_requests)
        monkeypatch.setattr(executor.file_utils, '_get_session', mock_session)
        secrets = self.executor._get_vault_secrets(taskdir=None)
        assert secrets == {}


        mock_requests = MockRequests({'data': [
                {
                  'description': 'dat_description, checkb_enable(fake://repo.git)',
                  'secrets': 'dem_secrets',
                  'uuid': 'dat uuid',
                }
             ]})
        mock_session = mock.Mock(return_value=mock_requests)
        monkeypatch.setattr(executor.file_utils, '_get_session', mock_session)
        secrets = self.executor._get_vault_secrets(taskdir=None)
        assert secrets == {'dat uuid': 'dem_secrets'}


