# -*- coding: utf-8 -*-
# Copyright 2009-2016, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import pytest
import mock
import os

from checkb.directives import koji_directive

ACTIONS = ('download', 'download_tag', 'download_latest_stable')
BUILD_LOG_ACTIONS = ('download', 'download_latest_stable')


class TestKojiDirective():
    def setup_method(self, method):
        self.koji_calls = ('get_nvr_rpms', 'get_tagged_rpms')

        self.ref_nvr = 'foo-1.2-3.fc99'
        self.ref_previous_nvr = 'foo-1.2-2.fc99'
        self.ref_arch = 'noarch'
        self.ref_tag = 'tagfoo'
        self.ref_targetdir = '/var/tmp/foo'
        self.ref_rpms = ['/var/tmp/fake/%s.%s.rpm'
                         % (self.ref_nvr, self.ref_arch)]

    def test_parse_download_command(self):
        self.ref_input = {'action': 'download',
                          'arch': self.ref_arch,
                          'koji_build': self.ref_nvr,
                          'target_dir': self.ref_targetdir}

        stub_koji = mock.Mock(**{'get_nvr_rpms.return_value': self.ref_rpms})
        test_helper = koji_directive.KojiDirective(stub_koji)

        test_helper.process(self.ref_input, None)

        getrpm_calls = stub_koji.get_nvr_rpms.call_args_list
        requested_nvr = getrpm_calls[0][0][0]
        requested_src = getrpm_calls[0][1]['src']
        requested_debuginfo = getrpm_calls[0][1]['debuginfo']

        assert len(getrpm_calls) == 1
        assert requested_nvr == self.ref_nvr
        assert not requested_src
        assert not requested_debuginfo

    def test_parse_download_tag_command(self):
        self.ref_input = {'action': 'download_tag',
                          'arch': self.ref_arch,
                          'koji_tag': self.ref_tag,
                          'target_dir': self.ref_targetdir}
        stub_koji = mock.Mock(
            **{'get_tagged_rpms.return_value': self.ref_rpms})
        test_helper = koji_directive.KojiDirective(stub_koji)

        test_helper.process(self.ref_input, None)

        getrpm_calls = stub_koji.get_tagged_rpms.call_args_list
        requested_tag = getrpm_calls[0][0][0]

        assert len(getrpm_calls) == 1
        assert requested_tag == self.ref_tag

    def test_parse_download_latest_stable_command(self):
        self.ref_input = {'action': 'download_latest_stable',
                          'arch': self.ref_arch,
                          'koji_build': self.ref_nvr,
                          'target_dir': self.ref_targetdir}
        stub_koji = mock.Mock(**
            {'get_nvr_rpms.return_value': self.ref_rpms,
             'latest_by_tag.return_value': self.ref_previous_nvr})
        test_helper = koji_directive.KojiDirective(stub_koji)

        test_helper.process(self.ref_input, None)

        getrpm_calls = stub_koji.get_nvr_rpms.call_args
        requested_nvr = getrpm_calls[0][0]
        requested_src = getrpm_calls[1]['src']
        requested_debuginfo = getrpm_calls[1]['debuginfo']

        koji_calls = stub_koji.method_calls
        assert len(koji_calls) == 2
        assert requested_nvr == self.ref_previous_nvr
        assert not requested_src
        assert not requested_debuginfo

    def test_download_latest_stable_no_builds(self):
        '''Don't do anything if there are no latest stable builds'''
        self.ref_input = {'action': 'download_latest_stable',
                          'arch': self.ref_arch,
                          'koji_build': self.ref_nvr,
                          'target_dir': self.ref_targetdir}
        stub_koji = mock.Mock(**{'latest_by_tag.return_value': None})
        test_helper = koji_directive.KojiDirective(stub_koji)

        retval = test_helper.process(self.ref_input, None)

        koji_calls = stub_koji.latest_by_tag.call_args_list
        assert len(koji_calls) == 1
        assert retval == {}

    @pytest.mark.parametrize('action', ACTIONS)
    def test_parse_multiple_arches(self, action):
        self.ref_arch = ['noarch', 'i386']
        ref_input = {'action': action, 'arch': self.ref_arch,
                     'koji_build': self.ref_nvr, 'koji_tag': self.ref_tag,
                     'target_dir': self.ref_targetdir}
        stub_koji = mock.Mock()
        test_helper = koji_directive.KojiDirective(stub_koji)

        test_helper.process(ref_input, None)

        getrpm_calls = [call for call in stub_koji.method_calls
            if call[0] in self.koji_calls]
        assert len(getrpm_calls) >= 1
        for call in getrpm_calls:
            requested_arches = call[2]['arches']
            assert requested_arches == self.ref_arch

    @pytest.mark.parametrize('action', ACTIONS)
    def test_parse_single_arch(self, action):
        ref_input = {'action': action, 'arch': self.ref_arch,
                     'koji_build': self.ref_nvr, 'koji_tag': self.ref_tag,
                     'target_dir': self.ref_targetdir}
        stub_koji = mock.Mock()
        test_helper = koji_directive.KojiDirective(stub_koji)

        test_helper.process(ref_input, None)

        getrpm_calls = [call for call in stub_koji.method_calls
            if call[0] in self.koji_calls]
        assert len(getrpm_calls) >= 1
        for call in getrpm_calls:
            requested_arches = call[2]['arches']
            assert requested_arches == [self.ref_arch]

    @pytest.mark.parametrize('action', ACTIONS)
    def test_parse_single_arch_as_list(self, action):
        ref_input = {'action': action, 'arch': [self.ref_arch],
                     'koji_build': self.ref_nvr, 'koji_tag': self.ref_tag,
                     'target_dir': self.ref_targetdir}
        stub_koji = mock.Mock()
        test_helper = koji_directive.KojiDirective(stub_koji)

        test_helper.process(ref_input, None)

        getrpm_calls = [call for call in stub_koji.method_calls
            if call[0] in self.koji_calls]
        assert len(getrpm_calls) >= 1
        for call in getrpm_calls:
            requested_arches = call[2]['arches']
            assert requested_arches == [self.ref_arch]

    @pytest.mark.parametrize('action', ACTIONS)
    def test_add_noarch(self, action):
        ref_input = {'action': action, 'arch': 'x86_64',
                     'koji_build': self.ref_nvr, 'koji_tag': self.ref_tag,
                     'target_dir': self.ref_targetdir}
        stub_koji = mock.Mock()
        test_helper = koji_directive.KojiDirective(stub_koji)

        test_helper.process(ref_input, None)

        getrpm_calls = [call for call in stub_koji.method_calls
            if call[0] in self.koji_calls]
        assert len(getrpm_calls) >= 1
        for call in getrpm_calls:
            requested_arches = call[2]['arches']
            for arch in ref_input['arch']:
                assert arch in requested_arches
            assert 'noarch' in requested_arches

    @pytest.mark.parametrize('action', ACTIONS)
    def test_exclude_arch(self, action):
        ref_input = {'action': action, 'arch': 'all',
                     'arch_exclude': ['x86_64', 'noarch'],
                     'koji_build': self.ref_nvr, 'koji_tag': self.ref_tag,
                     'target_dir': self.ref_targetdir}
        stub_koji = mock.Mock()
        test_helper = koji_directive.KojiDirective(stub_koji)

        test_helper.process(ref_input, None)

        getrpm_calls = [call for call in stub_koji.method_calls
            if call[0] in self.koji_calls]
        assert len(getrpm_calls) >= 1
        for call in getrpm_calls:
            requested_arches = call[2]['arches']
            excluded_arches = call[2]['arch_exclude']
            assert requested_arches == ref_input['arch']
            for arch in ref_input['arch_exclude']:
                assert arch in excluded_arches
            assert len(excluded_arches) == len(ref_input['arch_exclude'])

    @pytest.mark.parametrize('action', ACTIONS)
    def test_src(self, action):
        ref_input = {'action': action, 'arch': [], 'src': True,
                     'koji_build': self.ref_nvr, 'koji_tag': self.ref_tag,
                     'target_dir': self.ref_targetdir}
        stub_koji = mock.Mock()
        test_helper = koji_directive.KojiDirective(stub_koji)

        test_helper.process(ref_input, None)

        getrpm_calls = [call for call in stub_koji.method_calls
            if call[0] in self.koji_calls]
        assert len(getrpm_calls) >= 1
        for call in getrpm_calls:
            requested_arches = call[2]['arches']
            requested_src = call[2]['src']
            assert requested_arches == ref_input['arch']
            assert requested_src

    @pytest.mark.parametrize('action', ACTIONS)
    def test_debuginfo(self, action):
        ref_input = {'action': action, 'arch': [], 'debuginfo': True,
                     'koji_build': self.ref_nvr, 'koji_tag': self.ref_tag,
                     'target_dir': self.ref_targetdir}
        stub_koji = mock.Mock()
        test_helper = koji_directive.KojiDirective(stub_koji)

        test_helper.process(ref_input, None)

        getrpm_calls = [call for call in stub_koji.method_calls
            if call[0] in self.koji_calls]
        assert len(getrpm_calls) >= 1
        for call in getrpm_calls:
            requested_arches = call[2]['arches']
            requested_debuginfo = call[2]['debuginfo']
            assert requested_arches == ref_input['arch']
            assert requested_debuginfo

    @pytest.mark.parametrize('action', ACTIONS)
    def test_build_log_only_for_certain_actions(self, action):
        ref_input = {'action': action, 'arch': [], 'build_log': True,
                     'koji_build': self.ref_nvr, 'koji_tag': self.ref_tag,
                     'target_dir': self.ref_targetdir}
        stub_koji = mock.MagicMock()
        test_helper = koji_directive.KojiDirective(stub_koji)

        test_helper.process(ref_input, None)

        build_log_calls = [call for call in stub_koji.method_calls
            if call[0] == 'get_build_log']
        if action in BUILD_LOG_ACTIONS:
            assert len(build_log_calls) == 1
        else:
            assert len(build_log_calls) == 0

    @pytest.mark.parametrize('action', BUILD_LOG_ACTIONS)
    def test_build_log_return_value(self, action):
        ref_input = {'action': action, 'arch': [], 'build_log': True,
                     'koji_build': self.ref_nvr, 'koji_tag': self.ref_tag,
                     'target_dir': self.ref_targetdir}
        ref_get_bl_return = {'ok': ['/path/build.log.arch'],
            'error': ['some_arch']}
        stub_koji = mock.MagicMock()
        stub_koji.get_build_log.return_value = ref_get_bl_return
        test_helper = koji_directive.KojiDirective(stub_koji)

        retval = test_helper.process(ref_input, None)

        assert retval['downloaded_logs'] == ref_get_bl_return['ok']
        assert retval['log_errors'] == ref_get_bl_return['error']

    def test_mkdir_targetdir(self, tmpdir):
        rpmdir = tmpdir.join('rpmdir').strpath
        self.ref_input = {'action': 'download',
                          'arch': self.ref_arch,
                          'koji_build': self.ref_nvr,
                          'target_dir': rpmdir}
        stub_koji = mock.Mock(**{'get_nvr_rpms.return_value': self.ref_rpms})
        test_helper = koji_directive.KojiDirective(stub_koji)

        assert not os.path.exists(rpmdir)
        test_helper.process(self.ref_input, None)
        assert os.path.isdir(rpmdir)
