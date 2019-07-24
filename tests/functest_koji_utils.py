# -*- coding: utf-8 -*-
# Copyright 2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Functional tests for checkb/koji_utils.py'''

import mock
import os

from checkb.ext.fedora import koji_utils
from checkb import file_utils

from .test_file_utils import mock_download


class TestKojiClient():

    def setup_method(self, method):
        self.ref_nvr = 'foo-1.2-3.fc99'
        self.ref_arch = 'noarch'
        self.ref_name = 'foo'
        self.ref_version = '1.2'
        self.ref_release = '3.fc99'
        self.ref_buildid = 123456

        self.ref_build = {'package_name': self.ref_name,
                          'version': self.ref_version,
                          'release': self.ref_release,
                          'id': self.ref_buildid}

    def test_handle_norpms_in_build(self, tmpdir):
        """ This tests to make sure that missing rpms in a build are handled
        gracefully during download so that execution isn't stopped when a build
        is missing an rpm """

        rpmdir = tmpdir.mkdir("rpmdownload")
        stub_koji = mock.MagicMock(**{'getBuild.return_value': self.ref_build})
        test_koji = koji_utils.KojiClient(stub_koji)

        test_koji.get_nvr_rpms(self.ref_nvr, str(rpmdir), arches=[self.ref_arch])


    # === get_nvr_rpms ===

    def test_get_nvr_rpms_dest_exists(self, tmpdir, monkeypatch):
        '''Destination dir must be created even if no files are downloaded'''
        stub_koji = mock.Mock()
        test_koji = koji_utils.KojiClient(stub_koji)

        monkeypatch.setattr(test_koji, 'nvr_to_urls', lambda *args, **kwargs: [])
        monkeypatch.setattr(file_utils, 'download', mock_download)

        rpmdir = str(tmpdir.mkdir("rpmdownload")) + '/create_me'
        test_koji.get_nvr_rpms(self.ref_nvr, dest=rpmdir)

        assert os.path.isdir(rpmdir)

    # === get_tagged_rpms ===

    def test_get_tagged_rpms_dest_exists(self, tmpdir, monkeypatch):
        '''Destination dir must be created even if no files are downloaded'''
        stub_koji = mock.Mock(**{'listTagged.return_value': []})
        test_koji = koji_utils.KojiClient(stub_koji)
        stub_get_nvr_rpms = mock.Mock()

        monkeypatch.setattr(test_koji, 'get_nvr_rpms', stub_get_nvr_rpms)

        rpmdir = str(tmpdir.mkdir("rpmdownload")) + '/create_me'
        test_koji.get_tagged_rpms('some tag', dest=rpmdir)

        assert os.path.isdir(rpmdir)
