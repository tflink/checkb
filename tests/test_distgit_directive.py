# -*- coding: utf-8 -*-
# Copyright 2009-2015, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import os.path
import pytest
import mock

from checkb import file_utils
from checkb.directives import distgit_directive
import checkb.exceptions as exc
from checkb.ext.fedora import yumrepoinfo


@pytest.mark.usefixtures('setup')
class TestDistGitDirective():

    @pytest.fixture
    def setup(self, monkeypatch):
        self.ref_nvr = 'foo-1.2-3.fc99'
        self.ref_name = 'foo'
        self.ref_path = ['foo.spec']
        self.ref_localpath = ['local.foo.spec']
        self.ref_branch = 'f99'
        self.ref_namespace = 'rpms'
        self.baseurl = distgit_directive.BASEURL

        self.helper = distgit_directive.DistGitDirective()
        self.ref_input = {'nvr': self.ref_nvr,
                          'path': self.ref_path,
                          'target_dir': '/var/tmp/foo'}

        self.mock_download = mock.Mock()
        monkeypatch.setattr(file_utils, 'download', self.mock_download)

    def _get_url(self, path):
        return distgit_directive.URL_FMT.format(
            baseurl=self.baseurl,
            namespace=self.ref_namespace,
            package=self.ref_name,
            path=path,
            gitref=self.ref_branch)

    def test_download(self):
        self.helper.process(self.ref_input, None)

        download_calls = self.mock_download.call_args_list
        assert len(download_calls) == 1
        assert download_calls[0][0][0] == self._get_url(self.ref_path[0])
        assert download_calls[0][0][2] == os.path.join(self.ref_input['target_dir'],
                                                       self.ref_path[0])

    def test_localpath(self):
        self.ref_input['localpath'] = self.ref_localpath

        self.helper.process(self.ref_input, None)

        download_calls = self.mock_download.call_args_list
        assert len(download_calls) == 1
        assert download_calls[0][0][0] == self._get_url(self.ref_path[0])
        assert download_calls[0][0][2] == os.path.join(self.ref_input['target_dir'],
                                                       self.ref_localpath[0])

    def test_multiple_localpath(self):
        ref_path = ['file1', 'file2']
        ref_localpath = ['file3', 'file4']
        self.ref_input['path'] = ref_path
        self.ref_input['localpath'] = ref_localpath

        self.helper.process(self.ref_input, None)

        download_calls = self.mock_download.call_args_list
        assert len(download_calls) == 2
        assert download_calls[0][0][0] == self._get_url(ref_path[0])
        assert download_calls[1][0][0] == self._get_url(ref_path[1])
        assert download_calls[0][0][2] == os.path.join(self.ref_input['target_dir'],
                                                       ref_localpath[0])
        assert download_calls[1][0][2] == os.path.join(self.ref_input['target_dir'],
                                                       ref_localpath[1])

    def test_incorrect_localpath(self):
        self.ref_input['path'] = ['file1', 'file2']
        self.ref_input['localpath'] = ['file3']

        with pytest.raises(exc.CheckbValueError):
            self.helper.process(self.ref_input, None)

    def test_incorrect_path_str(self):
        self.ref_input['path'] = 'file1'

        with pytest.raises(exc.CheckbValueError):
            self.helper.process(self.ref_input, None)

    def test_incorrect_localpath_str(self):
        self.ref_input['localpath'] = 'file2'

        with pytest.raises(exc.CheckbValueError):
            self.helper.process(self.ref_input, None)

    def test_missing_package_or_nvr(self):
        self.ref_input.pop('nvr', None)
        self.ref_input.pop('package', None)

        with pytest.raises(exc.CheckbDirectiveError):
            self.helper.process(self.ref_input, None)

    def test_only_package(self):
        self.ref_input.pop('nvr', None)
        self.ref_input['package'] = self.ref_name
        self.ref_input['gitref'] = self.ref_branch

        self.helper.process(self.ref_input, None)

        download_calls = self.mock_download.call_args_list
        assert len(download_calls) == 1
        assert download_calls[0][0][0] == self._get_url(self.ref_path[0])

    def test_missing_path(self):
        self.ref_input.pop('path', None)

        with pytest.raises(exc.CheckbDirectiveError):
            self.helper.process(self.ref_input, None)

    def test_override_nvr(self):
        '''nvr parsing should be overriden when filling in parameters manually'''
        self.ref_name = 'bar'
        self.ref_branch = 'v17'
        self.ref_namespace = 'onions'
        self.ref_input.update({'nvr': self.ref_nvr,
                               'package': self.ref_name,
                               'gitref': self.ref_branch,
                               'namespace': self.ref_namespace})

        self.helper.process(self.ref_input, None)

        download_calls = self.mock_download.call_args_list
        assert len(download_calls) == 1
        # self.ref_nvr was not touched, so if nvr parsing gets priority, the URL will not match
        assert download_calls[0][0][0] == self._get_url(self.ref_path[0])

    def test_raises_on_404(self, monkeypatch):
        '''Directive must raise when file is missing in distgit (404)'''
        mock_download = mock.Mock(side_effect=exc.CheckbRemoteError('', errno=404))
        monkeypatch.setattr(file_utils, 'download', mock_download)

        with pytest.raises(exc.CheckbRemoteError):
            self.helper.process(self.ref_input, None)

    def test_ignore_404(self, monkeypatch):
        '''Directive ignores missing files (404) when ignore_missing is set to True'''
        mock_download = mock.Mock(side_effect=exc.CheckbRemoteError('', errno=404))
        monkeypatch.setattr(file_utils, 'download', mock_download)

        self.ref_input['ignore_missing'] = True

        self.helper.process(self.ref_input, None)

        mock_download.assert_called_once()

    def test_raises_on_non_404_with_ignore(self, monkeypatch):
        '''Directive must raise if ignore_missing is set to True but error is not 404'''
        mock_download = mock.Mock(side_effect=exc.CheckbRemoteError('', errno=503))
        monkeypatch.setattr(file_utils, 'download', mock_download)

        self.ref_input['ignore_missing'] = True

        with pytest.raises(exc.CheckbRemoteError):
            self.helper.process(self.ref_input, None)

    def test_ignore_404_on_some_files(self, monkeypatch):
        '''Directive returns list of downloaded files, missing files are ignored'''
        side_effects = [None, exc.CheckbRemoteError('', errno=404)]
        mock_download = mock.Mock(side_effect=side_effects)
        monkeypatch.setattr(file_utils, 'download', mock_download)

        self.ref_input['ignore_missing'] = True
        self.ref_input['path'] = ['foo.spec', 'foo.spek']

        downloaded = self.helper.process(self.ref_input, None)

        assert len(downloaded) == 1

    def test_gitref_rawhide(self):
        '''On rawhide, gitref must be "master"'''
        rawhide_tag = yumrepoinfo.YumRepoInfo().get('rawhide', 'tag')
        self.ref_nvr = 'foo-1.2-3.%s' % rawhide_tag.replace('f', 'fc')
        self.ref_input.update({'nvr': self.ref_nvr})
        self.ref_branch = 'master'

        self.helper.process(self.ref_input, None)

        download_calls = self.mock_download.call_args_list
        assert download_calls[0][0][0] == self._get_url(self.ref_path[0])
