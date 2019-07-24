# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Unit tests for checkb/directives/bodhi_directive.py'''

import pytest
import mock

from checkb.directives import bodhi_directive
from checkb.exceptions import CheckbDirectiveError
from checkb import config

class TestBodhiDownloads():

    def setup_method(self, method):
        '''Run this before every test invocation'''
        self.ref_arch = 'x86_64'
        self.ref_update_id = 'FEDORA-1234-56789'
        self.ref_targetdir = '/var/tmp/foo'
        self.ref_taskfile = '/foo/bar/task.yml'
        self.ref_nvr1 = 'foo-1.2.3.fc99'
        self.ref_nvr2 = 'bar-1.2.3.fc99'
        self.ref_update = {'title': 'Random update',
                       'builds': [{'nvr': self.ref_nvr1, 'package': {}},
                                  {'nvr': self.ref_nvr2, 'package': {}}
                                  ],
                       'other_keys': {}
                       }
        self.ref_input = {'action': 'download',
                          'arch': self.ref_arch,
                          'update_id': self.ref_update_id,
                          'target_dir': self.ref_targetdir,
                         }
        self.ref_rpmfile = '%s/%s.rpm' % (self.ref_targetdir, self.ref_nvr1)

        self.helper = bodhi_directive.BodhiDirective()
        self.stub_bodhi = mock.Mock(
            **{'get_update.return_value': self.ref_update})
        self.stub_koji = mock.Mock(
            **{'get_nvr_rpms.return_value': [self.ref_rpmfile]})


    def test_action_download_existing_update(self):
        '''Test download of existing update'''
        test_bodhi = bodhi_directive.BodhiDirective(self.stub_bodhi,
            self.stub_koji)

        output_data = test_bodhi.process(self.ref_input, None)

        ref_output_data = {'downloaded_rpms': [self.ref_rpmfile,
                                               self.ref_rpmfile]}
        getrpms_calls = self.stub_koji.get_nvr_rpms.call_args_list
        requested_nvrs = [call[0][0] for call in getrpms_calls]

        # checks whether get_nvr_rpms was called for every update
        # with correct nvrs
        assert len(getrpms_calls) == 2
        assert requested_nvrs == [self.ref_nvr1, self.ref_nvr2]
        assert output_data == ref_output_data


    def test_action_download_all_archs(self):
        '''Test download when all arches are demanded'''
        self.ref_input['arch'] = 'all'

        test_bodhi = bodhi_directive.BodhiDirective(self.stub_bodhi,
            self.stub_koji)

        test_bodhi.process(self.ref_input, None)

        ref_arches = set(config.get_config().supported_arches + ['noarch'])
        getrpms_calls = self.stub_koji.get_nvr_rpms.call_args_list
        req_arches = [call[0][2] for call in getrpms_calls]

        # checks whether all get_nvr_rpms calls demanded all arches
        assert all([set(arches) == ref_arches for arches in req_arches])

    def test_action_download_source(self):
        '''Test download of source packages'''
        self.ref_arch = []
        self.ref_input['arch'] = []
        self.ref_input['src'] = True

        test_bodhi = bodhi_directive.BodhiDirective(self.stub_bodhi,
            self.stub_koji)

        test_bodhi.process(self.ref_input, None)

        getrpms_calls = self.stub_koji.get_nvr_rpms.call_args_list

        # checks whether all get_nvr_rpms calls demanded only source pkgs
        assert all([call[0][2] == [] for call in getrpms_calls])
        assert all([call[1]['src'] for call in getrpms_calls])

    def test_action_download_multiple_arch(self):
        '''Test download of multiple arches packages'''
        self.ref_arch = ['x86_64', 'noarch']
        self.ref_input['arch'] = self.ref_arch

        test_bodhi = bodhi_directive.BodhiDirective(self.stub_bodhi,
            self.stub_koji)

        test_bodhi.process(self.ref_input, None)

        getrpms_calls = self.stub_koji.get_nvr_rpms.call_args_list
        req_arches = [call[0][2] for call in getrpms_calls]

        assert all([arches == self.ref_arch for arches in req_arches])

    def test_action_download_added_noarch(self):
        '''Test whether noarch is automaticaly added'''
        self.ref_input['arch'] = 'i386'

        test_bodhi = bodhi_directive.BodhiDirective(self.stub_bodhi,
            self.stub_koji)

        test_bodhi.process(self.ref_input, None)

        getrpms_calls = self.stub_koji.get_nvr_rpms.call_args_list
        req_arches = [call[0][2] for call in getrpms_calls]

        # checks whether noarch is demanded in all get_nvr_rpms calls
        assert all(['noarch' in arches for arches in req_arches])

    def test_action_download_nonexisting_update(self):
        '''Test whether exception is raised when no update is found'''
        stub_bodhi = mock.Mock(**{'get_update.return_value': None})
        stub_koji = mock.Mock(
            **{'get_nvr_rpms.return_value': "It shouldn't go this far"})

        test_bodhi = bodhi_directive.BodhiDirective(stub_bodhi, stub_koji)

        # No update is found, bodhi directive should raise an Exception
        with pytest.raises(CheckbDirectiveError):
            test_bodhi.process(self.ref_input, None)

    def test_invalid_action(self):
        '''Test response on non-existing action'''
        self.ref_input['action'] = 'foo'
        stub_bodhi = mock.Mock()
        stub_koji = mock.Mock()

        test_bodhi = bodhi_directive.BodhiDirective(stub_bodhi, stub_koji)

        # Unknown action should raise an Exception
        with pytest.raises(CheckbDirectiveError):
            test_bodhi.process(self.ref_input, None)

    def test_action_download_insufficient_params(self):
        '''Test response on unsufficient input for download action'''
        stub_bodhi = mock.Mock()
        stub_koji = mock.Mock()
        test_bodhi = bodhi_directive.BodhiDirective(stub_bodhi, stub_koji)

        for missing_arg in ['action', 'arch', 'update_id', 'target_dir']:
            ref_input = dict(self.ref_input)
            ref_input.pop(missing_arg)
            with pytest.raises(CheckbDirectiveError):
                test_bodhi.process(ref_input, None)
