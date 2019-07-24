# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import pytest
import mock
import os
import argparse

from checkb import main
from checkb import config
from checkb import check


@pytest.mark.usefixtures('setup')
class TestProcessArgs():

    @pytest.fixture
    def setup(self, monkeypatch):
        self.ref_artifactsdir = '/dir/'
        self.stub_config = mock.Mock(artifactsdir=self.ref_artifactsdir)
        self.stub_get_config = mock.Mock(return_value=self.stub_config)

        monkeypatch.setattr(config, 'get_config', self.stub_get_config)

        self.ref_input = {'arch': 'x86_64',
                          'item': 'foo-1.2-3.fc99',
                          'type': 'koji_build',
                          'taskdir': '/some/task',
                          'ssh': None,
                          'uuid': '20150930_153933_359680',
                          'override': []}

    def test_dont_modify_input(self):
        test_args = main.process_args(self.ref_input)
        assert test_args is not self.ref_input
        assert test_args != self.ref_input

    @pytest.mark.parametrize('itemtype', check.ReportType.list())
    def test_type(self, itemtype):
        self.ref_input['type'] = itemtype
        test_args = main.process_args(self.ref_input)
        assert test_args[itemtype] == self.ref_input['item']

    def test_orig_args(self):
        test_args = main.process_args(self.ref_input)
        assert test_args['_orig_args'] == self.ref_input

    def test_ssh(self):
        self.ref_input['ssh'] = 'root@127.0.0.1:33'
        test_args = main.process_args(self.ref_input)
        assert test_args['ssh'] == self.ref_input['ssh']
        assert test_args['user'] == 'root'
        assert test_args['machine'] == '127.0.0.1'
        assert test_args['port'] == 33

    def test_ssh_no_port(self):
        self.ref_input['ssh'] = 'root@127.0.0.1'
        test_args = main.process_args(self.ref_input)
        assert test_args['ssh'] == self.ref_input['ssh']
        assert test_args['user'] == 'root'
        assert test_args['machine'] == '127.0.0.1'
        assert test_args['port'] == 22

    def test_no_ssh(self):
        test_args = main.process_args(self.ref_input)
        assert 'user' not in test_args
        assert 'machine' not in test_args
        assert 'port' not in test_args

    def test_artifactsdir(self):
        test_args = main.process_args(self.ref_input)
        assert test_args['artifactsdir'] == os.path.join(self.ref_artifactsdir,
                                                         self.ref_input['uuid'])

    def test_taskdir(self):
        # absolute path should not be touched
        test_args = main.process_args(self.ref_input)
        assert test_args['taskdir'] == self.ref_input['taskdir']

        # relative path should get converted to absolute
        self.ref_input['taskdir'] = './task'
        test_args = main.process_args(self.ref_input)
        assert os.path.isabs(test_args['taskdir'])


@pytest.mark.usefixtures('setup')
class TestCheckArgs():

    @pytest.fixture
    def setup(self):
        self.empty_args = {'local': None, 'libvirt': None, 'ssh': None}

    def test_runmode_exclusive(self):
        '''allow only single runmode selection'''
        ref_params_bad = [{'local': True, 'ssh': 'user@machine'},
                          {'local': True, 'libvirt': True},
                          {'libvirt': True, 'ssh': 'user@machine'},
                          {'local': True, 'ssh': 'user@machine', 'libvirt': True}]
        ref_params_good = [{'local': True},
                           {'ssh': 'user@machine'},
                           {'libvirt': True},
                           {}]

        for ref_params in ref_params_bad:
            stub_error = mock.Mock()
            stub_parser = mock.Mock()
            stub_parser.error = stub_error
            args = self.empty_args.copy()
            args.update(ref_params)
            main.check_args(stub_parser, args)
            assert len(stub_error.mock_calls) == 1

        for ref_params in ref_params_good:
            stub_error = mock.Mock()
            stub_parser = mock.Mock()
            stub_parser.error = stub_error
            args = self.empty_args.copy()
            args.update(ref_params)
            main.check_args(stub_parser, args)
            assert len(stub_error.mock_calls) == 0

    def test_ssh_bad_usermachine(self):
        '''fail on invalid user@machine[:port] specifier'''
        ref_params = {'ssh': 'user#machine'}

        stub_error = mock.Mock()
        stub_parser = mock.Mock()
        stub_parser.error = stub_error
        args = self.empty_args
        args.update(ref_params)
        main.check_args(stub_parser, args)

        assert len(stub_error.mock_calls) == 1


class TestGetParser():

    def test_parser_creation(self):
        '''make sure the parser doesn't crash when created'''
        parser = main.get_argparser()
        assert isinstance(parser, argparse.ArgumentParser)
