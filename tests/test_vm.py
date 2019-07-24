# -*- coding: utf-8 -*-
# Copyright 2009-2015, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import pytest
from mock import Mock, MagicMock

from checkb.ext.disposable import vm
from checkb import exceptions as exc

from testcloud import image, instance
import testcloud.exceptions as tce


class TestvmImagePrepare(object):
    '''Test checkb.vm._prepare_image'''

    def setup_method(self, method):
        self.ref_uuid = '1234-5678-9012'

    def should_raise_on_failure(self, monkeypatch):
        stub_image = Mock(side_effect=tce.TestcloudImageError())

        monkeypatch.setattr(image, 'Image', stub_image)
        monkeypatch.setattr(vm.ImageFinder, 'get_latest_metadata', Mock())

        test_vm = vm.TestCloudMachine(self.ref_uuid)

        with pytest.raises(exc.CheckbImageError):
            test_vm._prepare_image(distro=None, release=None, flavor=None,
                arch=None)

    def should_behave_on_success(self, monkeypatch):
        stub_image = MagicMock()

        monkeypatch.setattr(image, 'Image', stub_image)
        monkeypatch.setattr(vm.ImageFinder, 'get_latest_metadata', Mock())

        test_vm = vm.TestCloudMachine(self.ref_uuid)

        test_vm._prepare_image(distro=None, release=None, flavor=None,
            arch=None)


class TestvmInstancePrepare(object):
    '''Test checkb.vm._prepare_instance'''

    def setup_method(self, method):
        self.ref_uuid = '1234-5678-9012'

    def should_make_proper_calls(self, monkeypatch):
        stub_image = Mock()
        stub_instance = MagicMock()
        stub_instanceclass = Mock(return_value=stub_instance)

        monkeypatch.setattr(instance, 'Instance', stub_instanceclass)

        test_vm = vm.TestCloudMachine(self.ref_uuid)

        test_vm._prepare_instance(stub_image)

        assert stub_instance.method_calls == [('prepare',), ('spawn_vm',), ('start',)]


class TestvmTeardown(object):
    '''Test checkb.vm.teardown() method'''

    def setup_method(self, method):
        self.ref_uuid = '1234-5678-9012'

    def should_be_quiet_on_success(self, monkeypatch):
        test_vm = vm.TestCloudMachine(self.ref_uuid)
        mock_instance = Mock()
        mock_check_instance = Mock(return_value=mock_instance)
        monkeypatch.setattr(test_vm, '_check_existing_instance', mock_check_instance)

        test_vm.teardown()
        assert len(mock_instance.mock_calls) == 1

    def should_raise_on_failure(self, monkeypatch):
        test_vm = vm.TestCloudMachine(self.ref_uuid)
        mock_instance = Mock()
        mock_instance.remove.side_effect = tce.TestcloudInstanceError()
        mock_check_instance = Mock(return_value=mock_instance)
        monkeypatch.setattr(test_vm, '_check_existing_instance', mock_check_instance)

        with pytest.raises(exc.CheckbRemoteError):
            test_vm.teardown()


class TestvmExistingInstances(object):
    '''Test the possible outcomes of checking for existing instances. Exception
    should be thrown if the should_exist arg doesn't match "reality".'''

    def setup_method(self, method):
        self.ref_uuid = '1234-5678-9012'

    def should_raise_existing_expecting_novm(self, monkeypatch):
        stub_instance = Mock(return_value=None)

        monkeypatch.setattr(instance, 'find_instance', stub_instance)

        test_vm = vm.TestCloudMachine(self.ref_uuid)

        with pytest.raises(exc.CheckbRemoteError):
            test_vm._check_existing_instance(True)

    def should_return_none_expecting_novm(self, monkeypatch):
        stub_instance = Mock(return_value=None)

        monkeypatch.setattr(instance, 'find_instance', stub_instance)

        test_vm = vm.TestCloudMachine(self.ref_uuid)

        test_instance = test_vm._check_existing_instance(False)

        assert test_instance is None

    def should_return_instance_found_expecting_vm(self, monkeypatch):
        stub_found_instance = Mock()
        stub_instance = Mock(return_value=stub_found_instance)

        monkeypatch.setattr(instance, 'find_instance', stub_instance)

        test_vm = vm.TestCloudMachine(self.ref_uuid)

        test_instance = test_vm._check_existing_instance(True)

        assert test_instance == stub_found_instance

    def should_raise_noexisting_expecting_vm(self, monkeypatch):
        stub_found_instance = Mock()
        stub_instance = Mock(return_value=stub_found_instance)

        monkeypatch.setattr(instance, 'find_instance', stub_instance)

        test_vm = vm.TestCloudMachine(self.ref_uuid)

        with pytest.raises(exc.CheckbRemoteError):
            test_vm._check_existing_instance(False)


@pytest.mark.usefixtures("setup")
class TestImageLatest:

    @pytest.fixture
    def setup(self, monkeypatch):
        self.images = ['151008_0427-fedora-23-cloud-x86_64.qcow2',
                       'ubuntu-fabulous-fedora.qcow2',
                       '151008_0223-fedora-23-minimal-i386.qcow2',
                       '151105_0100-server-x86_64.qcow2',
                       'el_capitan.iso',
                       '151008_0100-server.qcow2',
                       '151007_0516-fedora-23-minimal-x86_64.qcow2',
                       '151007_0516-fedora-rawhide-minimal-x86_64.qcow2',
                       'windows10.raw',
                       '151008_0315-fedora-23-minimal-i386.qcow2',
                       '151008_0315-fedora-23-minimal-x86_64.qcow2',
                       '151008_0315-ubuntu-fabulous_fanthom-minimal-x86_64.qcow2']
        self.stub_list_images = Mock()
        monkeypatch.setattr(vm.ImageFinder, 'get_all_filenames', self.stub_list_images)


    def test_dir_populated(self):
        self.stub_list_images.return_value = self.images

        assert vm.ImageFinder.get_latest_metadata('fedora', '23', 'minimal', 'i386', '')['filename'] ==\
            '151008_0315-fedora-23-minimal-i386.qcow2'
        assert vm.ImageFinder.get_latest_metadata('fedora', '23', 'minimal', 'x86_64', '')['filename'] ==\
            '151008_0315-fedora-23-minimal-x86_64.qcow2'
        assert vm.ImageFinder.get_latest_metadata('ubuntu', 'fabulous_fanthom', 'minimal', 'x86_64', '')['filename'] ==\
            '151008_0315-ubuntu-fabulous_fanthom-minimal-x86_64.qcow2'


    def test_dir_populated_single(self):
        self.stub_list_images.return_value = self.images

        assert vm.ImageFinder.get_latest_metadata('fedora', '23', 'cloud', 'x86_64', '')['filename'] ==\
            '151008_0427-fedora-23-cloud-x86_64.qcow2'
        assert vm.ImageFinder.get_latest_metadata('fedora', 'rawhide', 'minimal', 'x86_64', '')['filename'] ==\
            '151007_0516-fedora-rawhide-minimal-x86_64.qcow2'

    def test_dir_empty(self):
        self.stub_list_images.return_value = []

        assert vm.ImageFinder.get_latest_metadata('fedora', '23', 'minimal', '') is None

    def test_no_such_image(self):
        self.stub_list_images.return_value = self.images

        assert vm.ImageFinder.get_latest_metadata('fedora', '69', 'ultimate', '') is None
