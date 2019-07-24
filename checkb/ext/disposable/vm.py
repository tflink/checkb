# -*- coding: utf-8 -*-
# Copyright 2009-2015, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing


"""Interface to locally spawned virtual machines that are used as disposable
clients for executing Checkb tasks."""

from time import sleep, time
import socket
import getpass
import re
import os

from checkb.logger import log
from checkb import config
import checkb.exceptions as exc

from testcloud import instance, image
from testcloud.exceptions import TestcloudInstanceError, TestcloudImageError


class TestCloudMachine(object):
    '''Launch virtual machines with TestCloud and prepare them for executing
    tasks (install packages etc.)'''

    def __init__(self, uuid):
        ''':param uuid: unicode string uuid for the task being executed'''

        #: name of the testcloud instance spawned for this task
        self.instancename = 'checkb-{}'.format(uuid)

        #: username to use when connecting to the virtual machine
        self.username = 'root'

        #: password for user on the remote machine
        self.password = 'passw0rd'

        #: ip address of the remote machine (only set after prepared and spawned successfully)
        self.ipaddr = None

        #: uuid of the task which spawned this instance
        self.uuid = uuid

        #: hostname to use for spawned instance - based on username of current user
        self.hostname = 'checkb-%s' % getpass.getuser()

    def _prepare_image(self, distro, release, flavor, arch):
        '''Use testcloud to prepare an image for local booting
        :param str distro: Distro to use in image discovery
        :param str release: Distro's release to use in image discovery
        :param str flavor: base-image flavor to use in image discovery
        :param str arch: arch to use in image discovery
        :raises CheckbImageNotFoundError: when base image of the required type is not found
        :raises CheckbImageError: for errors in preparing the image with testcloud
        '''

        tc_image = None

        try:
            if config.get_config().force_imageurl:
                img_url = config.get_config().imageurl
            else:
                log.debug("Looking for image with DISTRO: %s, RELEASE: %s, FLAVOR: %s, ARCH: %s" %
                          (distro, release, flavor, arch))

                img_url = ImageFinder.get_latest(
                    distro=distro,
                    release=release,
                    flavor=flavor,
                    arch=arch
                    )
        except exc.CheckbImageNotFoundError as e:
            log.error(e)
            raise

        log.debug("Preparing image {} for task {}".format(img_url, self.uuid))

        try:
            tc_image = image.Image(img_url)
            # symlink the image instead of copying it to the testcloud dir, because our user only
            # expects image handling in checkb dirs, and we remove all minion instances
            # immediately after task execution anyway
            tc_image.prepare(copy=False)
        except TestcloudImageError as e:
            log.exception(e)
            raise exc.CheckbImageError("There was an error while preparing the "
                                           "testcloud image", e)

        return tc_image

    def _prepare_instance(self, tc_image):
        '''Prepare an instance for booting and boot it with testcloud'''
        log.debug("preparing testcloud instance {}".format(self.instancename))
        tc_instance = instance.Instance(self.instancename, tc_image, hostname=self.hostname)
        tc_instance.prepare()

        log.debug("spawning testcloud instance {}".format(self.instancename))
        tc_instance.spawn_vm()
        tc_instance.start()

    def _check_existing_instance(self, should_exist=False):
        '''Check whether an instance with the same name already exists, raise errors if the result
        was not as expected.

        :param should_exist: sets expectation on whether the instance should
                             exist already or not
        :raises CheckbRemoteError: if the preset expectation is not met
        '''
        existing_instance = instance.find_instance(self.instancename)

        if existing_instance is None:
            if should_exist:
                raise exc.CheckbRemoteError("Was expecting to find instance {} but it does not"
                                               " already exist".format(self.instancename))
        else:
            if not should_exist:
                raise exc.CheckbRemoteError("Expected to NOT find instance {} but it is "
                                               "already defined".format(self.instancename))
        return existing_instance

    def prepare(self, distro, release, flavor, arch):
        '''Prepare a virtual machine for running tasks.
        :param str distro: Distro to use in image discovery
        :param str release: Distro's release to use in image discovery
        :param str flavor: base-image flavor to use in image discovery
        :param str arch: arch to use in image discovery

        :raises CheckbRemoteError: if there are any errors while preparing
                                      the virtual machine.
       '''

        tc_image = self._prepare_image(distro, release, flavor, arch)
        self._check_existing_instance(should_exist=False)
        self._prepare_instance(tc_image)
        tc_instance = instance.find_instance(self.instancename)
        self.ipaddr = tc_instance.get_ip()

    def wait_for_port(self, port, timeout=60):
        '''Wait until port is open. Repeatedly tries to socket.connect on given port.

        :param port: port to check
        :param timeout: timeout in seconds
        :raises CheckbInstanceError: when timeouted
        '''
        s = socket.socket()
        start_time = time()
        log.debug('Waiting up to %d seconds for %s:%s to open.' % (timeout, self.ipaddr, port))
        while True:
            try:
                s.connect((self.ipaddr, port))
            except socket.error:
                pass
            else:
                s.close()
                break
            if (start_time + timeout) < time():
                raise TestcloudInstanceError("Waiting for %s:%s to open timed out (%ds)" %
                                             (self.ipaddr, port, timeout))

            sleep(0.1)

    def teardown(self):
        '''Tear down the virtual machine by stopping it and removing it from the host machine.

        :raises CheckbRemoteError: if there is a failure while stopping or removing the virtual
                                      machine instance
        '''
        tc_instance = self._check_existing_instance(should_exist=True)
        try:
            tc_instance.remove(autostop=True)
        except TestcloudInstanceError as e:
            log.exception("Error while tearing down instance {}".format(self.instancename))
            raise exc.CheckbRemoteError(e)


class ImageFinder(object):
    '''Retrieve images from either local or remote sources'''

    @classmethod
    def get_all_filenames(cls, imagesdir=None):
        """Get list of images present on the system.

        :param imagesdir: absolute path to directory containing the images, path from config is
                          used if None
        """

        if not imagesdir:
            imagesdir = config.get_config().imagesdir

        return os.listdir(imagesdir)

    @classmethod
    def get_latest(cls, distro, release, flavor, arch='x86_64', imagesdir=None):
        """Search for the most recent image available on the system.

        :param distro: distro of the image (e.g. ``fedora``)
        :param release: release of the image (e.g. ``23``)
        :param flavor: flavor of the image (e.g. ``minimal``)
        :param imagesdir: absolute path to directory containing the images, path from config is
                          used if None
        :param arch: architecture of the image

        :return: file:// url of the latest image available
        :raises CheckbImageError: if no such image for given release and flavor was found
        """

        if not imagesdir:
            imagesdir = config.get_config().imagesdir

        latest_metadata = cls.get_latest_metadata(distro, release, flavor, arch, imagesdir)

        if not latest_metadata:
            raise exc.CheckbImageNotFoundError(
                'No image for DISTRO: %s, RELEASE: %s, FLAVOR: %s, ARCH: %s in %s' %
                (distro, release, flavor, arch, imagesdir))
        else:
            url = "file://" + os.path.join(imagesdir, latest_metadata['filename'])
            log.debug("Found image: %s" % url)
            return url

    @classmethod
    def get_latest_metadata(cls, distro, release, flavor, arch='x86_64', imagesdir=None):
        """Search for the most recent image available on the system.

        :param distro: distro of the image (e.g. ``fedora``)
        :param release: release of the image (e.g. ``23``)
        :param flavor: flavor of the image (e.g. ``minimal``)
        :param imagesdir: absolute path to directory containing the images, path from config is
                          used if None
        :param arch: arch of the image (e.g. 'x86_64')

        :return: metadata of the most recent image
        :rtype: dict {'date': str, 'version': str, 'release': str, 'arch': str, 'filename': str}
        """

        if not imagesdir:
            imagesdir = config.get_config().imagesdir

        release = str(release)
        # The pattern is: YYMMDD_HHMM-DISTRO-RELEASE-FLAVOR-ARCH.(qcow2|raw|img)
        # For example:    160301_1030-fedora-23-checkb_cloud-x86_64.img
        pattern = re.compile(r'^([0-9]{6}_[0-9]{4})-(.*?)-(.*?)-(.*?)-(.*?)\.(qcow2|raw|img)$')

        images = []
        for filename in cls.get_all_filenames(imagesdir):
            m = pattern.match(filename)
            if m:
                images.append({'timestamp': m.group(1),
                               'distro': m.group(2),
                               'release': m.group(3),
                               'flavor': m.group(4),
                               'arch': m.group(5),
                               'filename': filename})

        filtered = [
            i for i in images if
            i['distro'] == distro and i['release'] == release and
            i['flavor'] == flavor and i['arch'] == arch
            ]
        if not filtered:
            return None
        else:
            return sorted(filtered, key=lambda i: i['timestamp'])[-1]
