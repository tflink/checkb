# -*- coding: utf-8 -*-
# Copyright 2009-2016, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Unit tests for checkb/koji_utils.py'''

import pytest
import os
import itertools
import mock
import koji

from checkb.ext.fedora import koji_utils
from checkb import exceptions as exc
from checkb import config
from checkb import file_utils
from checkb import arch_utils

from .test_file_utils import mock_download

# http://stackoverflow.com/questions/3190706/nonlocal-keyword-in-python-2-x
def create_multicall(first, second):
    first_call = {"value": True}

    def multicall():
        if first_call["value"]:
            first_call["value"] = False
            return first
        else:
            return second

    return multicall


class TestKojiClient(object):
    def setup_method(self, method):
        self.ref_nvr = 'foo-1.2-3.fc99'
        self.ref_latest_stable = 'foo-1.2-2.fc99'
        self.ref_arch = 'x86_64'
        self.ref_name = 'foo'
        self.ref_version = '1.2'
        self.ref_release = '3.fc99'
        self.ref_buildid = 123456
        self.ref_filename = "%s.%s.rpm" % (self.ref_nvr, self.ref_arch)
        self.ref_tags = ['f99-updates', 'f99']

        self.ref_build = {'package_name': self.ref_name,
                          'version': self.ref_version,
                          'release': self.ref_release,
                          'id': self.ref_buildid,
                          'nvr': '%s-%s-%s' % (self.ref_name, self.ref_version,
                                               self.ref_release)}

    @property
    def ref_rpms(self):
        # rpms: standard, src, 3x debuginfo, noarch
        return [{'name': self.ref_name, 'version': self.ref_version,
                 'release': self.ref_release, 'nvr': self.ref_nvr,
                 'arch': self.ref_arch, 'build_id': self.ref_buildid},
                {'name': self.ref_name, 'version': self.ref_version,
                 'release': self.ref_release, 'nvr': self.ref_nvr,
                 'arch': 'src', 'build_id': self.ref_buildid},
                {'name': self.ref_name + '-debuginfo',
                 'version': self.ref_version,
                 'release': self.ref_release, 'nvr': self.ref_nvr,
                 'arch': self.ref_arch, 'build_id': self.ref_buildid},
                {'name': self.ref_name + '-debuginfo-common',
                 'version': self.ref_version,
                 'release': self.ref_release, 'nvr': self.ref_nvr,
                 'arch': self.ref_arch, 'build_id': self.ref_buildid},
                {'name': self.ref_name + '-debugsource',
                 'version': self.ref_version,
                 'release': self.ref_release, 'nvr': self.ref_nvr,
                 'arch': self.ref_arch, 'build_id': self.ref_buildid},
                {'name': self.ref_name + '-data',
                 'version': self.ref_version,
                 'release': self.ref_release, 'nvr': self.ref_nvr,
                 'arch': 'noarch', 'build_id': self.ref_buildid}]

    # =====================
    #    latest_by_tag()
    # =====================

    def test_latest_by_tag_first_tag_miss(self):
        stub_koji = mock.Mock(**
            {'listTagged.return_value': None,
             'multiCall.return_value': [
                [[]], [[{'nvr': self.ref_latest_stable}]]
                ]
            })

        test_koji = koji_utils.KojiClient(stub_koji)
        outcome = test_koji.latest_by_tag(self.ref_tags, self.ref_name)

        assert outcome == self.ref_latest_stable

    def test_latest_by_tag_second_tag_miss(self):
        stub_koji = mock.Mock(**
            {'listTagged.return_value': None,
             'multiCall.return_value': [
                [[{'nvr': self.ref_latest_stable}]], [[]]
                ]
            })

        test_koji = koji_utils.KojiClient(stub_koji)
        outcome = test_koji.latest_by_tag(self.ref_tags, self.ref_name)

        assert outcome == self.ref_latest_stable

    def test_latest_by_tag_build_not_found(self):
        stub_koji = mock.Mock(**
            {'listTagged.return_value': None,
             'multiCall.return_value': [
                [[]], [[]]
                ]
            })

        test_koji = koji_utils.KojiClient(stub_koji)
        assert test_koji.latest_by_tag(self.ref_tags, self.ref_name) is None

    # =====================
    #    rpms_to_build()
    # =====================

    def test_rpms_to_build(self):
        stub_koji = mock.Mock(**
            {'getBuild.return_value': None,
             'getRPM.return_value': None,
             'multiCall': create_multicall(
                [[self.ref_rpms[0]], [self.ref_rpms[1]]],
                [[self.ref_build], [self.ref_build]])
            })

        test_koji = koji_utils.KojiClient(stub_koji)
        outcome = test_koji.rpms_to_build([self.ref_filename,self.ref_filename])

        assert outcome == [self.ref_build, self.ref_build]
        # because two rpms come from same build, it gets called twice for each
        # rpm, once for build
        assert len(stub_koji.mock_calls) == 3

    def test_rpms_to_build_exceptions(self):
        stub_koji = mock.Mock(**
            {'getRPM.return_value': None,
             'multiCall.return_value':
                [{"faultCode": -1, "faultString": "failed"}]
            })
        test_koji = koji_utils.KojiClient(stub_koji)

        with pytest.raises(exc.CheckbRemoteError):
            test_koji.rpms_to_build([self.ref_filename])

        stub_koji = mock.Mock(**
            {'getBuild.return_value': None,
             'getRPM.return_value': None,
             'multiCall': create_multicall(
                [[self.ref_rpms[0]]],
                [{"faultCode": -1, "faultString": "failed"}])
            })

        test_koji = koji_utils.KojiClient(stub_koji)
        with pytest.raises(exc.CheckbRemoteError):
            test_koji.rpms_to_build([self.ref_filename])

        stub_koji = mock.Mock(**
            {'getBuild.return_value': None,
             'getRPM.return_value': None,
             'multiCall.return_value': [[None]],
            })

        test_koji = koji_utils.KojiClient(stub_koji)
        with pytest.raises(exc.CheckbRemoteError):
            test_koji.rpms_to_build([self.ref_filename])

        stub_koji = mock.Mock(**
            {'getBuild.return_value': None,
             'getRPM.return_value': None,
             'multiCall': create_multicall(
                [[self.ref_rpms[0]]], [[None]]),
            })

        test_koji = koji_utils.KojiClient(stub_koji)
        with pytest.raises(exc.CheckbRemoteError):
            test_koji.rpms_to_build([self.ref_filename])

    # =====================
    #    _compute_arches()
    # =====================

    def test_add_binary_arches(self):
        '''specifying basearch should add all binary arches'''
        ref_arch = 'i386'
        bin_arches = arch_utils.Arches.binary[ref_arch]
        arches = koji_utils.KojiClient._compute_arches(arches=[ref_arch], arch_exclude=[],
                                                       src=False)
        assert arches == set(bin_arches)

    def test_keep_extra_arch_with_all(self):
        '''Arches should not be thrown away even if 'all' is specified (there might be some extra
        obscure arches specified in addition)'''
        ref_arch = ['all', 'obscure_arch']
        arches = koji_utils.KojiClient._compute_arches(arches=ref_arch, arch_exclude=[], src=False)
        assert 'all' not in arches
        assert 'obscure_arch' in arches

    def test_src(self):
        # src enabled
        ref_arch = ['all']
        arches = koji_utils.KojiClient._compute_arches(arches=ref_arch, arch_exclude=[], src=True)
        assert 'src' in arches

        # src disabled
        ref_arch = ['all', 'src']
        arches = koji_utils.KojiClient._compute_arches(arches=ref_arch, arch_exclude=[], src=False)
        assert 'src' not in arches

    def test_only_src(self):
        ref_arch = []
        arches = koji_utils.KojiClient._compute_arches(arches=ref_arch, arch_exclude=[], src=True)
        assert arches == set(['src'])

    def test_arch_exclude(self):
        ref_arch = ['all']

        # arch_exclude disabled
        ref_exclude = []
        arches = koji_utils.KojiClient._compute_arches(arches=ref_arch, arch_exclude=ref_exclude,
                                                       src=False)
        for arch in ref_exclude:
            if arch in config.get_config().supported_arches:
                assert arch in arches

        # arch_exclude enabled
        ref_exclude = ['x86_64']
        arches = koji_utils.KojiClient._compute_arches(arches=ref_arch, arch_exclude=ref_exclude,
                                                       src=False)
        for arch in ref_exclude:
            assert arch not in arches

    def test_arch_exclude_override_explicit(self):
        '''arch_exclude should work even when the same arch is explicitly stated in arches'''
        ref_exclude = ['x86_64']
        ref_arch = ref_exclude + ['i386']

        arches = koji_utils.KojiClient._compute_arches(arches=ref_arch, arch_exclude=ref_exclude,
                                                       src=False)
        for arch in ref_exclude:
            assert arch not in arches

    # ===================
    #    nvr_to_urls()
    # ===================

    def test_get_urls(self):
        stub_koji = mock.Mock(**
            {'getBuild.return_value': self.ref_build,
             'listRPMs.return_value': self.ref_rpms,
            })
        test_koji = koji_utils.KojiClient(stub_koji)
        koji_baseurl = config.get_config().pkg_url

        test_urls = test_koji.nvr_to_urls(self.ref_nvr)
        for url in test_urls:
            assert url.startswith(koji_baseurl)
            assert url.endswith('.rpm')

    def should_not_throw_exception_norpms(self):
        '''It's possible to have no RPMs (for the given arch) in a build'''
        stub_koji = mock.MagicMock(**
            {'getBuild.return_value': self.ref_build,
            })
        test_koji = koji_utils.KojiClient(stub_koji)

        test_koji.nvr_to_urls(self.ref_nvr, arches = [self.ref_arch])

    def test_nvr_to_urls_debuginfo(self):
        stub_koji = mock.Mock(**
            {'getBuild.return_value': self.ref_build,
             'listRPMs.return_value': self.ref_rpms,
            })
        test_koji = koji_utils.KojiClient(stub_koji)

        # debuginfo enabled
        urls = test_koji.nvr_to_urls(self.ref_nvr, debuginfo=True)
        assert len(urls) == len(self.ref_rpms)
        assert any(['debuginfo' in url for url in urls])

        # debuginfo disabled
        urls = test_koji.nvr_to_urls(self.ref_nvr, debuginfo=False)
        assert len(urls) == len([rpm for rpm in self.ref_rpms
                                 if 'debug' not in rpm['name']])
        assert all(['debuginfo' not in url for url in urls])

    def should_not_query_no_arch_no_src(self):
        '''If there's no arch to query for, should not perform the query'''
        stub_koji = mock.Mock()
        test_koji = koji_utils.KojiClient(stub_koji)

        test_koji.nvr_to_urls(self.ref_nvr, arches=[], src=False)
        assert not stub_koji.called

    # ====================
    #    get_nvr_rpms()
    # ====================

    def test_get_nvr_rpms_simple(self, monkeypatch):
        '''NVR contains a few RPMs'''
        test_koji = koji_utils.KojiClient(mock.Mock())

        stub_urls = [
            'http://localhost/file1.rpm',
            'http://localhost/file2.rpm']
        monkeypatch.setattr(test_koji, 'nvr_to_urls',
                            lambda *args, **kwargs: stub_urls)
        monkeypatch.setattr(file_utils, 'download', mock_download)
        monkeypatch.setattr(file_utils, 'makedirs', mock.Mock())

        rpmdir = '/fake'
        rpm_files = test_koji.get_nvr_rpms(self.ref_nvr, dest=rpmdir)

        assert rpm_files == [
            os.path.join(rpmdir, 'file1.rpm'),
            os.path.join(rpmdir, 'file2.rpm')]

    def test_get_nvr_rpms_empty(self, monkeypatch):
        '''NVR contains no RPMs (e.g. of a particular arch)'''
        test_koji = koji_utils.KojiClient(mock.Mock())

        monkeypatch.setattr(test_koji, 'nvr_to_urls', lambda *args, **kwargs: [])
        monkeypatch.setattr(file_utils, 'download', mock_download)
        monkeypatch.setattr(file_utils, 'makedirs', mock.Mock())

        rpmdir = '/fake'
        rpm_files = test_koji.get_nvr_rpms(self.ref_nvr, dest=rpmdir)

        assert rpm_files == []

    def test_get_nvr_rpms_production_profile(self, monkeypatch):
        '''caching should be disabled in production profile'''
        test_koji = koji_utils.KojiClient(mock.Mock())
        stub_download = mock.Mock()

        monkeypatch.setattr(test_koji, 'nvr_to_urls',
                            lambda *args, **kwargs: ['foo'])
        monkeypatch.setattr(file_utils, 'download', stub_download)
        monkeypatch.setattr(file_utils, 'makedirs', mock.Mock())
        monkeypatch.setattr(config, '_config', config.ProductionConfig)

        rpmdir = '/fake'
        test_koji.get_nvr_rpms(self.ref_nvr, dest=rpmdir)

        call = stub_download.call_args
        assert call[1]['cachedir'] is None

    def test_get_nvr_rpms_development_profile(self, monkeypatch):
        '''caching should be disabled in development profile'''
        test_koji = koji_utils.KojiClient(mock.Mock())
        stub_download = mock.Mock()

        monkeypatch.setattr(test_koji, 'nvr_to_urls',
                            lambda *args, **kwargs: ['foo'])
        monkeypatch.setattr(file_utils, 'download', stub_download)
        monkeypatch.setattr(file_utils, 'makedirs', mock.Mock())
        monkeypatch.setattr(config, '_config', config.Config)

        rpmdir = '/fake'
        test_koji.get_nvr_rpms(self.ref_nvr, dest=rpmdir)

        call = stub_download.call_args
        assert call[1]['cachedir'] is not None

    # =======================
    #    get_tagged_rpms()
    # =======================

    def test_get_tagged_rpms_single(self, monkeypatch):
        '''Single NVR in a tag'''
        stub_koji = mock.Mock(**
            {'listTagged.return_value': [self.ref_build]
            })
        test_koji = koji_utils.KojiClient(stub_koji)

        stub_rpms = [
            '/fake/file1.rpm',
            '/fake/file2.rpm']
        monkeypatch.setattr(test_koji, 'get_nvr_rpms',
                            lambda *args, **kwargs: stub_rpms)
        monkeypatch.setattr(file_utils, 'makedirs', lambda *args, **kwargs: None)

        rpm_files = test_koji.get_tagged_rpms('some tag', dest=None)

        assert rpm_files == stub_rpms

    def test_get_tagged_rpms_multiple(self, monkeypatch):
        '''Multiple NVRs in a tag'''
        stub_koji = mock.Mock(**
            {'listTagged.return_value': [self.ref_build, {'nvr': 'bar-1-1'}]
            })
        test_koji = koji_utils.KojiClient(stub_koji)
        stub_rpms = {self.ref_build['nvr']: ['/fake/file1.rpm',
                                             '/fake/file2.rpm'],
                     'bar-1-1': ['/fake/bar1.rpm']
                    }
        monkeypatch.setattr(test_koji, 'get_nvr_rpms',
                            lambda nvr, *args, **kwargs: stub_rpms[nvr])
        monkeypatch.setattr(file_utils, 'makedirs', lambda *args, **kwargs: None)

        rpm_files = test_koji.get_tagged_rpms('some tag', dest=None)

        assert sorted(rpm_files) == sorted(itertools.chain(*stub_rpms.values()))

    def test_get_tagged_rpms_none(self, monkeypatch):
        '''No NVRs in a tag'''
        stub_koji = mock.Mock(**
            {'listTagged.return_value': [],
            })
        test_koji = koji_utils.KojiClient(stub_koji)
        stub_get_nvr_rpms = mock.Mock()

        monkeypatch.setattr(test_koji, 'get_nvr_rpms', stub_get_nvr_rpms)
        monkeypatch.setattr(file_utils, 'makedirs', lambda *args, **kwargs: None)

        rpm_files = test_koji.get_tagged_rpms('some tag', dest=None)

        assert rpm_files == []
        # get_nvr_rpms() should not be called
        stub_get_nvr_rpms.assert_not_called()

    # =====================
    #    get_build_log()
    # =====================

    def test_build_log_no_build(self):
        '''raise error if build info can't be retrieved'''
        stub_koji = mock.Mock()
        stub_koji.listBuildRPMs.side_effect = koji.GenericError()
        test_koji = koji_utils.KojiClient(stub_koji)

        with pytest.raises(exc.CheckbRemoteError):
            test_koji.get_build_log(self.ref_nvr, dest=None)

    def test_build_log_do_nothing_different_arch(self, monkeypatch):
        '''if only unavailable arches are requested, do nothing and don't crash'''
        ref_arch = 'armv7hl'  # not available in self.rpms
        stub_koji = mock.Mock()
        stub_koji.listBuildRPMs.return_value = self.ref_rpms
        test_koji = koji_utils.KojiClient(stub_koji)
        stub_download = mock.Mock()
        monkeypatch.setattr(file_utils, 'download', stub_download)

        test_koji.get_build_log(self.ref_nvr, dest=None, arches=[ref_arch])

        assert stub_download.call_count == 0

    def test_build_log_dont_download_src(self, monkeypatch):
        '''src logs should not be attempted to be downloaded'''
        ref_archs = ('all', 'src')
        stub_koji = mock.Mock()
        stub_koji.listBuildRPMs.return_value = self.ref_rpms
        test_koji = koji_utils.KojiClient(stub_koji)
        stub_download = mock.Mock()
        monkeypatch.setattr(file_utils, 'download', stub_download)

        test_koji.get_build_log(self.ref_nvr, dest=None, arches=ref_archs)

        assert stub_download.call_count > 0
        for call in stub_download.call_args_list:
            assert '/src/' not in call[1]['url']

    def test_build_log_return_value(self, monkeypatch):
        '''populate return values for working and failed downloads'''
        ref_dest = '/path/'

        def fake_download(url, dirname, filename, *args, **kwargs):
            if '/noarch/' in url:
                raise exc.CheckbRemoteError()
            else:
                return os.path.join(ref_dest, filename)

        stub_koji = mock.Mock()
        stub_koji.listBuildRPMs.return_value = self.ref_rpms
        test_koji = koji_utils.KojiClient(stub_koji)
        stub_download = mock.Mock()
        stub_download.side_effect = fake_download
        monkeypatch.setattr(file_utils, 'download', stub_download)

        retval = test_koji.get_build_log(self.ref_nvr, dest=ref_dest, arches=['all'])

        assert stub_download.call_count == 2  # x86_64 and noarch
        assert retval['ok'] == [os.path.join(ref_dest, 'build.log.x86_64')]
        assert retval['error'] == ['noarch']

    def test_build_log_correct_url(self, monkeypatch):
        '''the url to be downloaded must be created correctly'''
        stub_koji = mock.Mock()
        stub_koji.listBuildRPMs.return_value = self.ref_rpms
        test_koji = koji_utils.KojiClient(stub_koji)
        stub_download = mock.Mock()
        monkeypatch.setattr(file_utils, 'download', stub_download)

        test_koji.get_build_log(self.ref_nvr, dest=None, arches=[self.ref_arch])

        assert stub_download.call_count == 1
        call = stub_download.call_args
        for part in (self.ref_name, self.ref_version, self.ref_release, self.ref_arch):
            assert '/%s/' % part in call[1]['url']
        assert call[1]['url'].startswith(config.get_config().pkg_url)
        assert call[1]['url'].endswith('/build.log')


class TestGetENVR(object):

    def test_epoch(self):
        '''Epoch included in build'''
        build = {'nvr': 'foo-1.2-3.fc20',
                 'epoch': 1,
                }
        assert koji_utils.getNEVR(build) == 'foo-1:1.2-3.fc20'

    def test_no_epoch(self):
        '''Epoch not included in build'''
        build = {'nvr': 'foo-1.2-3.fc20',
                 'epoch': None,
                }
        assert koji_utils.getNEVR(build) == 'foo-1.2-3.fc20'

    def test_raise(self):
        '''Invalid input param'''
        with pytest.raises(exc.CheckbValueError):
            koji_utils.getNEVR('foo-1.2-3.fc20')
