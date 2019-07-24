# -*- coding: utf-8 -*-
# Copyright 2018, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Unit tests for checkb/executor.py'''

import pytest
import mock
import signal
import os
import json
import subprocess
import yaml

from checkb import executor
import checkb.exceptions as exc
from checkb.directives import resultsdb_directive
from checkb import os_utils
from checkb.ext.disposable import vm
from checkb import config
import testcloud.exceptions

PLAYBOOK='''
- hosts: localhost
  # this saves a lot of time when running in mock (without network)
  gather_facts: no
  vars:
    checkb_generic_task: true
  tasks:
    - debug:
        msg: This is a sample debug printout from a Checkb generic task
'''


@pytest.mark.usefixtures('setup')
class TestExecutor():

    @pytest.fixture
    def setup(self, tmpdir, monkeypatch):
        '''Run this before every test invocation'''
        self.artifactsdir = tmpdir.mkdir('artifacts')
        self.taskdir = tmpdir.mkdir('taskdir')
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
            'uuid': 'random-uuid',
            'no_destroy': False
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
        self.conf.spawn_vm_retries = 5

    def test_interrupt_handler(self):
        '''Raise correct exception for an interrupt'''

        signals = {
            1: 'SIGHUP',
            2: 'SIGINT',
            3: 'SIGQUIT',
            15: 'SIGTERM',
            99: 'UNKNOWN',
        }

        for (signum, signame) in signals.items():
            try:
                self.executor._interrupt_handler(signum, None)
            except exc.CheckbInterruptError as e:
                assert e.signum == signum
                assert e.signame == signame
                assert str(e.signum) in str(e)
                assert e.signame in str(e)

    def test_report_results(self, monkeypatch):
        '''Report results using resultsdb if results file exists'''
        playbook = 'playbook.yml'
        resultsfile = self.artifactsdir.mkdir(playbook).mkdir(
            'checkb').join('results.yml')
        resultsfile.ensure()

        mock_rdb = mock.Mock()
        monkeypatch.setattr(resultsdb_directive, 'ResultsdbDirective',
            mock_rdb)
        rdb_instance = mock_rdb.return_value

        self.executor._report_results(playbook)
        mock_rdb.assert_called_once()  # create instance
        rdb_instance.process.assert_called_once()
        assert rdb_instance.process.call_args[1]['params']['file'] == \
            resultsfile.strpath
        assert rdb_instance.process.call_args[1]['arg_data'] == \
            self.arg_data

    def test_report_results_missing_file(self, monkeypatch):
        '''Raise when no results file exists'''
        with pytest.raises(exc.CheckbDirectiveError):
            self.executor._report_results('missing-playbook-dir')

    def test_run_playbook(self, monkeypatch):
        '''A standard invocation of ansible-playbook'''
        mock_signal = mock.Mock()
        monkeypatch.setattr(signal, 'signal', mock_signal)
        mock_popen = mock.Mock(return_value=('fake output', None))
        monkeypatch.setattr(os_utils, 'popen_rt', mock_popen)

        output = self.executor._run_playbook(self.playbook_name,
            self.ipaddr, self.playbook_vars)

        # must return playbook output
        assert output == 'fake output'

        # must mask signals
        assert mock_signal.call_count == 4  # 2 signals masked, then reset

        # must export ansible vars
        varsfile = os.path.join(self.artifactsdir.strpath, self.playbook_name,
            'checkb', 'task_vars.json')
        allvarsfile = os.path.join(self.artifactsdir.strpath,
            self.playbook_name, 'checkb', 'internal_vars.json')
        for vf in [varsfile, allvarsfile]:
            assert os.path.isfile(vf)
            with open(vf, 'r') as f:
                json.load(f)

        # must run ansible-playbook
        mock_popen.assert_called_once()
        cmd_args = mock_popen.call_args[0][0]
        assert cmd_args[0] == 'ansible-playbook'
        assert '--inventory={},'.format(self.ipaddr) in cmd_args
        assert '--extra-vars=@{}'.format(allvarsfile) in cmd_args
        assert '--become' in cmd_args
        assert '--connection=local' in cmd_args

    def test_run_playbook_failed(self, monkeypatch):
        '''Should raise when ansible-playbook fails'''
        mock_signal = mock.Mock()
        monkeypatch.setattr(signal, 'signal', mock_signal)
        cpe = subprocess.CalledProcessError(returncode=99, cmd='fake')
        mock_popen = mock.Mock(side_effect=cpe)
        monkeypatch.setattr(os_utils, 'popen_rt', mock_popen)

        with pytest.raises(exc.CheckbError):
            self.executor._run_playbook(self.playbook_name, self.ipaddr,
                self.playbook_vars)

        # must unmask signals even when playbook failed
        assert mock_signal.call_count == 4  # 2 signals masked, then reset

        # must run ansible-playbook
        mock_popen.assert_called_once()

    def test_run_playbook_interrupted(self, monkeypatch):
        '''Should try failsafe stop when interrupted'''
        mock_signal = mock.Mock()
        monkeypatch.setattr(signal, 'signal', mock_signal)
        error = exc.CheckbInterruptError(15, 'SIGTERM')
        mock_popen = mock.Mock(side_effect=[error, mock.DEFAULT])
        monkeypatch.setattr(os_utils, 'popen_rt', mock_popen)

        with pytest.raises(exc.CheckbInterruptError):
            self.executor._run_playbook(self.playbook_name, self.ipaddr,
                self.playbook_vars)

        # must unmask signals even when playbook failed
        assert mock_signal.call_count == 4  # 2 signals masked, then reset

        # must run ansible-playbook twice, fist normal, second failsafe
        assert mock_popen.call_count == 2
        assert '--tags' in mock_popen.call_args_list[1][0][0]
        assert 'failsafe' in mock_popen.call_args_list[1][0][0]

    def test_run_playbook_failsafe_error(self, monkeypatch):
        '''When failsafe stop gives an error, it should be ignored'''
        # don't override Ctrl+C during testing
        mock_signal = mock.Mock()
        monkeypatch.setattr(signal, 'signal', mock_signal)
        error = exc.CheckbInterruptError(15, 'SIGTERM')
        cpe = subprocess.CalledProcessError(returncode=99, cmd='fake')
        mock_popen = mock.Mock(side_effect=[error, cpe])
        monkeypatch.setattr(os_utils, 'popen_rt', mock_popen)

        with pytest.raises(exc.CheckbInterruptError):
            self.executor._run_playbook(self.playbook_name, self.ipaddr,
                self.playbook_vars)

    def test_run_playbook_forwarded_vars(self, monkeypatch):
        '''Only certain vars should get forwarded to task playbook, no other'''
        # don't override Ctrl+C during testing
        mock_signal = mock.Mock()
        monkeypatch.setattr(signal, 'signal', mock_signal)
        mock_popen = mock.Mock(return_value=('fake output', None))
        monkeypatch.setattr(os_utils, 'popen_rt', mock_popen)

        self.executor._run_playbook(self.playbook_name,
            self.ipaddr, self.playbook_vars)
        varsfile = os.path.join(self.artifactsdir.strpath, self.playbook_name,
            'checkb', 'task_vars.json')

        assert os.path.isfile(varsfile)
        with open(varsfile, 'r') as vf:
            vars_ = json.load(vf)

        for var in executor.Executor.FORWARDED_VARS:
            assert var in vars_
        assert len(vars_) == len(executor.Executor.FORWARDED_VARS)

    def test_get_client_ipaddr_local(self):
        '''Local execution'''
        self.arg_data['local'] = True
        self.arg_data['libvirt'] = False
        self.arg_data['ssh'] = False
        self.executor = executor.Executor(self.arg_data)

        ipaddr = self.executor._get_client_ipaddr()

        assert ipaddr == '127.0.0.1'
        assert self.executor.run_remotely == False

    def test_get_client_ipaddr_libvirt(self):
        '''Libvirt execution'''
        self.arg_data['local'] = False
        self.arg_data['libvirt'] = True
        self.arg_data['ssh'] = False
        self.executor = executor.Executor(self.arg_data)

        ipaddr = self.executor._get_client_ipaddr()

        assert ipaddr == None
        assert self.executor.run_remotely == True

    def test_get_client_ipaddr_ssh(self):
        '''Ssh execution'''
        self.arg_data['local'] = False
        self.arg_data['libvirt'] = False
        self.arg_data['ssh'] = True
        self.arg_data['machine'] = '127.0.0.2'
        self.executor = executor.Executor(self.arg_data)

        ipaddr = self.executor._get_client_ipaddr()

        assert ipaddr == '127.0.0.2'
        assert self.executor.run_remotely == True

    def test_execute_local(self, monkeypatch):
        '''Execution using local mode'''
        mock_check_syntax = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_check_playbook_syntax',
            mock_check_syntax)
        mock_spawn_vm = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_spawn_vm', mock_spawn_vm)
        mock_run_playbook = mock.Mock(return_value=(None, True))
        monkeypatch.setattr(executor.Executor, '_run_playbook',
            mock_run_playbook)
        mock_report_results = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_report_results',
            mock_report_results)
        self.executor.ipaddr = '127.0.0.1'
        self.executor.run_remotely = False

        success = self.executor.execute()

        assert success == True
        mock_check_syntax.assert_called_once()
        mock_spawn_vm.assert_not_called()
        mock_run_playbook.assert_called_once()
        assert mock_run_playbook.call_args[0][1] == '127.0.0.1'
        mock_report_results.assert_called_once()

    def test_execute_ssh(self, monkeypatch):
        '''Execution using ssh mode'''
        mock_check_syntax = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_check_playbook_syntax',
            mock_check_syntax)
        mock_spawn_vm = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_spawn_vm', mock_spawn_vm)
        mock_run_playbook = mock.Mock(return_value=(None, True))
        monkeypatch.setattr(executor.Executor, '_run_playbook',
            mock_run_playbook)
        mock_report_results = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_report_results',
            mock_report_results)
        self.executor.ipaddr = '127.0.0.2'
        self.executor.run_remotely = True

        success = self.executor.execute()

        assert success == True
        mock_check_syntax.assert_called_once()
        mock_spawn_vm.assert_not_called()
        mock_run_playbook.assert_called_once()
        assert mock_run_playbook.call_args[0][1] == '127.0.0.2'
        mock_report_results.assert_called_once()

    def test_execute_libvirt(self, monkeypatch):
        '''Execution using libvirt mode'''
        mock_check_syntax = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_check_playbook_syntax',
            mock_check_syntax)
        mock_spawn_vm = mock.Mock(return_value='127.0.0.3')
        monkeypatch.setattr(executor.Executor, '_spawn_vm', mock_spawn_vm)
        mock_run_playbook = mock.Mock(return_value=(None, True))
        monkeypatch.setattr(executor.Executor, '_run_playbook',
            mock_run_playbook)
        mock_report_results = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_report_results',
            mock_report_results)
        mock_task_vm = mock.Mock()
        self.executor.task_vm = mock_task_vm
        self.executor.ipaddr = None
        self.executor.run_remotely = True

        success = self.executor.execute()

        assert success == True
        mock_check_syntax.assert_called_once()
        mock_spawn_vm.assert_called_once()
        mock_run_playbook.assert_called_once()
        assert mock_run_playbook.call_args[0][1] == '127.0.0.3'
        mock_report_results.assert_called_once()
        mock_task_vm.teardown.assert_called_once()

    def test_execute_libvirt_no_destroy(self, monkeypatch):
        '''Execution using libvirt mode'''
        mock_check_syntax = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_check_playbook_syntax',
            mock_check_syntax)
        mock_spawn_vm = mock.Mock(return_value='127.0.0.3')
        monkeypatch.setattr(executor.Executor, '_spawn_vm', mock_spawn_vm)
        mock_run_playbook = mock.Mock(return_value=(None, True))
        monkeypatch.setattr(executor.Executor, '_run_playbook',
            mock_run_playbook)
        mock_report_results = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_report_results',
            mock_report_results)
        mock_task_vm = mock.Mock()
        self.executor.task_vm = mock_task_vm
        self.executor.ipaddr = None
        self.executor.run_remotely = True

        self.arg_data['no_destroy'] = True

        success = self.executor.execute()

        assert success == True
        mock_check_syntax.assert_called_once()
        mock_spawn_vm.assert_called_once()
        mock_run_playbook.assert_called_once()
        assert mock_run_playbook.call_args[0][1] == '127.0.0.3'
        mock_report_results.assert_called_once()
        mock_task_vm.teardown.assert_not_called()

    def test_execute_no_playbooks(self, monkeypatch):
        '''Should raise when there are no playbooks'''
        mock_check_syntax = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_check_playbook_syntax',
            mock_check_syntax)
        mock_run_playbook = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_run_playbook',
            mock_run_playbook)
        mock_report_results = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_report_results',
            mock_report_results)
        self.playbook.remove()

        with pytest.raises(exc.CheckbError):
            self.executor.execute()

        mock_check_syntax.assert_not_called()
        mock_run_playbook.assert_not_called()
        mock_report_results.assert_not_called()

    def test_execute_more_playbooks(self, monkeypatch):
        '''Should execute all found playbooks'''
        mock_check_syntax = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_check_playbook_syntax',
            mock_check_syntax)
        mock_run_playbook = mock.Mock(return_value=(None, True))
        monkeypatch.setattr(executor.Executor, '_run_playbook',
            mock_run_playbook)
        mock_report_results = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_report_results',
            mock_report_results)
        self.playbook.copy(self.taskdir.join('tests_copy.yml'))

        success = self.executor.execute()

        assert success == True
        assert mock_check_syntax.call_count == 2
        assert mock_run_playbook.call_count == 2
        playbooks = [
            mock_run_playbook.call_args_list[0][0][0],
            mock_run_playbook.call_args_list[1][0][0]
        ]
        assert 'tests.yml' in playbooks
        assert 'tests_copy.yml' in playbooks
        assert mock_report_results.call_count == 2
        playbooks = [
            mock_report_results.call_args_list[0][0][0],
            mock_report_results.call_args_list[1][0][0]
        ]
        assert 'tests.yml' in playbooks
        assert 'tests_copy.yml' in playbooks

    def test_execute_error(self, monkeypatch):
        '''Should raise on playbook errors'''
        mock_check_syntax = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_check_playbook_syntax',
            mock_check_syntax)
        mock_run_playbook = mock.Mock(side_effect=exc.CheckbError)
        monkeypatch.setattr(executor.Executor, '_run_playbook',
            mock_run_playbook)
        mock_report_results = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_report_results',
            mock_report_results)

        success = self.executor.execute()

        assert success == False
        mock_check_syntax.assert_called_once()
        mock_run_playbook.assert_called_once()
        mock_report_results.assert_not_called()

    def test_execute_not_checkb_task(self, monkeypatch):
        '''Should raise error when not marked as a checkb generic task'''
        playbook = yaml.safe_load(PLAYBOOK)[0]
        playbook['vars'].pop('checkb_generic_task')
        self.playbook.remove()
        self.playbook.write(yaml.safe_dump([playbook]))
        monkeypatch.setattr(executor.Executor, '_check_playbook_syntax',
            mock.Mock())
        mock_run_playbook = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_run_playbook',
            mock_run_playbook)

        success = self.executor.execute()

        assert success == False
        mock_run_playbook.assert_not_called()

    @pytest.mark.parametrize('checkb_generic_task', [False, None])
    def test_execute_checkb_task_False(self, monkeypatch,
        checkb_generic_task):
        '''Should raise error when checkb_generic_task is False'''
        playbook = yaml.safe_load(PLAYBOOK)[0]
        playbook['vars']['checkb_generic_task'] = checkb_generic_task
        self.playbook.remove()
        self.playbook.write(yaml.safe_dump([playbook]))
        mock_run_playbook = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_check_playbook_syntax',
            mock.Mock())
        monkeypatch.setattr(executor.Executor, '_run_playbook',
            mock_run_playbook)

        success = self.executor.execute()

        assert success == False
        mock_run_playbook.assert_not_called()

    def test_execute_more_playbooks_error(self, monkeypatch):
        '''Should execute all found playbooks even if some has error'''
        mock_check_syntax = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_check_playbook_syntax',
            mock_check_syntax)
        mock_run_playbook = mock.Mock(side_effect=[
            exc.CheckbError,
            (None, True)])
        monkeypatch.setattr(executor.Executor, '_run_playbook',
            mock_run_playbook)
        mock_report_results = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_report_results',
            mock_report_results)
        self.playbook.copy(self.taskdir.join('tests_copy.yml'))

        success = self.executor.execute()

        assert success == False
        assert mock_check_syntax.call_count == 2
        assert mock_run_playbook.call_count == 2
        playbooks = [
            mock_run_playbook.call_args_list[0][0][0],
            mock_run_playbook.call_args_list[1][0][0]
        ]
        assert 'tests.yml' in playbooks
        assert 'tests_copy.yml' in playbooks
        assert mock_report_results.call_count == 1
        playbooks = [
            mock_report_results.call_args_list[0][0][0]
        ]
        assert 'tests.yml' in playbooks or 'tests_copy.yml' in playbooks

    def test_execute_interrupted(self, monkeypatch):
        '''Should halt execution and return when interrupted'''
        mock_check_syntax = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_check_playbook_syntax',
            mock_check_syntax)
        error = exc.CheckbInterruptError(15, 'SIGTERM')
        mock_run_playbook = mock.Mock(side_effect=error)
        monkeypatch.setattr(executor.Executor, '_run_playbook',
            mock_run_playbook)
        mock_report_results = mock.Mock()
        monkeypatch.setattr(executor.Executor, '_report_results',
            mock_report_results)
        self.playbook.copy(self.taskdir.join('tests_copy.yml'))

        success = self.executor.execute()

        assert success == False
        mock_check_syntax.assert_called_once()
        mock_run_playbook.assert_called_once()
        mock_report_results.assert_not_called()

    def test_spawn_vm_retries(self, monkeypatch):
        '''Spawning VM should be attempted several times on failure'''
        mock_vm_prepare = mock.Mock(
            side_effect=[testcloud.exceptions.TestcloudInstanceError,
                mock.DEFAULT])
        mock_vm = mock.Mock()
        vm_instance = mock_vm.return_value
        vm_instance.prepare = mock_vm_prepare
        vm_instance.ipaddr = '10.11.12.13'
        monkeypatch.setattr(vm, 'TestCloudMachine', mock_vm)

        ipaddr = self.executor._spawn_vm(None, self.playbook_vars)
        assert ipaddr == '10.11.12.13'
        assert mock_vm_prepare.call_count == 2

    def test_spawn_vm_complete_fail(self, monkeypatch):
        '''Exception should be raised when VM can't be spawned using retries'''
        mock_vm_prepare = mock.Mock(
            side_effect=testcloud.exceptions.TestcloudInstanceError)
        mock_vm = mock.Mock(return_value=mock.Mock(prepare=mock_vm_prepare))
        monkeypatch.setattr(vm, 'TestCloudMachine', mock_vm)

        with pytest.raises(exc.CheckbMinionError):
            self.executor._spawn_vm(None, self.playbook_vars)

        assert mock_vm_prepare.call_count == self.conf.spawn_vm_retries

    def test_load_playbook_accepted_vars(self):
        '''All accepted vars must be loaded and none other'''
        playbook = yaml.safe_load(PLAYBOOK)[0]
        playbook['vars'].clear()
        # add all accepted
        for var in executor.Executor.ACCEPTED_VARS:
            playbook['vars'][var] = 'This is ' + var
        # add unaccepted starting with checkb_
        playbook['vars']['checkb_unaccepted'] = 'ignore me'
        # add unaccepted generic
        playbook['vars']['unaccepted'] = 'ignore me'
        self.playbook.remove()
        self.playbook.write(yaml.safe_dump([playbook]))

        vars_ = self.executor._load_playbook_vars(self.playbook_name)

        for var in executor.Executor.ACCEPTED_VARS:
            assert var in vars_
        assert 'checkb_unaccepted' not in vars_
        assert 'unaccepted' not in vars_
        assert len(vars_) == len(executor.Executor.ACCEPTED_VARS)
