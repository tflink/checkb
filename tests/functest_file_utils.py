# -*- coding: utf-8 -*-
# Copyright 2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Functional tests for checkb/file_utils.py'''

import os
import pytest
import mock
import requests
from checkb import file_utils
from checkb import exceptions as exc


class TestSameLength():

    def test_nonexistent_file(self, tmpdir):
        """Should not crash if the file doesn't exist"""
        fpath = tmpdir.join('nonexistent.file').strpath
        assert file_utils._same_length(fpath, None) is False


@pytest.mark.usefixtures('setup')
class TestDownload():

    @pytest.fixture
    def setup(self, tmpdir, monkeypatch):
        """Run this before every test method execution start"""
        self.dirname = tmpdir.join('download').strpath
        self.cachedir = tmpdir.join('cachedir').strpath
        self._download_mocked = mock.Mock()
        monkeypatch.setattr(file_utils, '_download', self._download_mocked)

    def test_create_dirname(self, tmpdir):
        """output dir should get created if it doesn't exist, multiple levels"""
        dirname = tmpdir.join('parentdir/subdir').strpath
        assert not os.path.exists(dirname)
        file_utils.download(url='http://localhost/file', dirname=dirname)
        assert os.path.isdir(dirname)

    def test_filename_missing(self):
        """filename should be automatically derived"""
        file_utils.download(url='http://localhost/file.xyz', dirname=self.dirname)
        self._download_mocked.assert_called_with('http://localhost/file.xyz',
                                                 os.path.join(self.dirname, 'file.xyz'))

    def test_filename_provided(self):
        """filename should be respected when provided"""
        file_utils.download(url='http://localhost/file.xyz', dirname=self.dirname,
                            filename='important.file')

        self._download_mocked.assert_called_with('http://localhost/file.xyz',
                                                 os.path.join(self.dirname, 'important.file'))

    def test_create_cachedir(self):
        """cachedir should be created if it doesn't exist"""
        assert not os.path.exists(self.cachedir)
        file_utils.download(url='http://localhost/file', dirname=self.dirname,
                            cachedir=self.cachedir)
        assert os.path.isdir(self.cachedir)

    def test_cache_used(self):
        """file should be downloaded to cache if cachedir is defined"""
        file_utils.download(url='http://localhost/file.xyz', dirname=self.dirname,
                            cachedir=self.cachedir)
        self._download_mocked.assert_called_with('http://localhost/file.xyz',
                                                 os.path.join(self.cachedir, 'file.xyz'))

    def test_cache_not_used(self):
        """file should not be downloaded to cache if cachedir is not defined"""
        file_utils.download(url='http://localhost/file', dirname=self.dirname)
        assert not self._download_mocked.call_args[0][1].startswith(self.cachedir)

    def test_skip_download_if_cached(self, tmpdir, monkeypatch):
        """if the file is already in cache, it should not be downloaded again"""
        tmpdir.mkdir('download').join('file').write('data')
        stub_same_length = lambda *args, **kwargs: True
        monkeypatch.setattr(file_utils, '_same_length', stub_same_length)

        file_utils.download(url='http://localhost/file', dirname=self.dirname)
        assert self._download_mocked.call_count == 0

    def test_create_symlink(self):
        """symlink should be created if the download is cached"""
        file_utils.download(url='http://localhost/file', dirname=self.dirname,
                            cachedir=self.cachedir)
        assert os.path.islink(os.path.join(self.dirname, 'file'))

    def test_skip_symlink(self):
        """symlink should not be in dirname if the download is not cached"""
        file_utils.download(url='http://localhost/file', dirname=self.dirname)
        assert not os.path.islink(os.path.join(self.dirname, 'file'))

    def test_return_value(self):
        """downloaded file path should be returned"""
        path = file_utils.download(url='http://localhost/file', dirname=self.dirname)
        assert path == os.path.join(self.dirname, 'file')

    def test_raise(self, monkeypatch):
        """download errors should be raised"""
        mock_response = mock.Mock(status_code=404)
        _download_mocked = mock.Mock(side_effect=(
            requests.exceptions.RequestException('fake download failed', response=mock_response)))
        monkeypatch.setattr(file_utils, '_download', _download_mocked)

        with pytest.raises(exc.CheckbRemoteError):
            file_utils.download(url='http://localhost/file', dirname=self.dirname)
