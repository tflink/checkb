# -*- coding: utf-8 -*-
# Copyright 2009-2016, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

from __future__ import absolute_import

from checkb.directives import BaseDirective
import checkb.exceptions as exc
from checkb.ext.fedora.koji_utils import KojiClient
from checkb.ext.fedora import rpm_utils
from checkb.logger import log
from checkb.python_utils import basestring
from checkb import file_utils

DOCUMENTATION = """
module: koji_directive
short_description: download builds and tags from Koji
description: |
  The koji directive interfaces with `Koji <http://koji.fedoraproject.org/>`_
  to facilitate various Koji actions. You can either download all RPMs from
  a specific build, or you can download all RPMs from all builds belonging
  to a specific Koji tag.
parameters:
  action:
    required: true
    description: |
      Set the main mode of operation:

      * ``download``: download a single build
      * ``download_tag``: download all builds belonging to a Koji tag
      * ``download_latest_stable``: download the latest build (of the same package you provide in
        ``koji_build``) that is currently in stable Fedora repositories (main or updates repo). If
        there's no such build, do nothing.
    type: str
    choices: [download, download_tag, download_latest_stable]
  arch:
    required: true
    description: |
      an architecture (or a list of architectures) for which to download RPMs for the requested
      build/tag. If you want to download RPMs for all Checkb-supported arches, use ``'all'``.
      If you don't want to download any binary arch (i.e. you're only interested in SRPMs, which is
      controlled by `src` option), use an empty list ``[]``.

      Note: ``noarch`` RPMs are always automatically downloaded unless ``arch=[]``,
      or you specifically exclude them using ``arch_exclude``. Also, if you specify base arches
      (like ``i386``), all concrete binary arches for that base arch will be automatically added
      (e.g. ``i[3-6]86``).
    type: str or list of str
    choices: [supported architectures, all]
  arch_exclude:
    required: false
    description: |
      an architecture (or a list of architectures) to exclude from downloading (overrides ``arch``
      value). You can use it to exclude some specific archicture while using ``arch='all'``.
      Example: ``['armhfp', 'noarch']``
    type: str or list of str
    choices: [supported architectures]
  build_log:
    required: false
    description: download also ``build.log`` files for each requested architecture (the files will
      be saved as ``build.log.<arch>``). Note that some logs can be already deleted in Koji and
      might not be available for download. Such missing logs will be skipped. This option will be
      considered only for single build downloads (i.e. ``action='download'`` or
      ``action='download_latest_stable'``).
    type: bool
    default: False
  debuginfo:
    required: false
    description: download also ``debuginfo`` RPM files
    type: bool
    default: False
  koji_build:
    required: true
    description: |
      N(E)VR of a Koji build to download (for ``action="download"``) or to search
      the latest stable build for (for ``action="download_latest_stable"``). Not
      required for ``action="download_tag"``. Example: ``xchat-2.8.8-21.fc20``
    type: str
  koji_tag:
    required: true
    description: |
      name of a Koji tag to download all builds from. Only required when
      ``action="download_tag"``. Example: ``f20-updates-pending``
    type: str
  src:
    required: false
    description: download also ``src`` RPM files
    type: bool
    default: False
  target_dir:
    required: true
    description: directory into which to download builds. It gets created if it doesn't exist.
    type: str
returns: |
  A dictionary containing following items:

  * ``downloaded_rpms``: (list of str) a list of absolute paths of the downloaded RPMs
  * ``downloaded_logs``: (list of str) a list of absolute paths of the downloaded build logs
  * ``log_errors``: (list of str) a list of architectures for which the ``build.log`` could not be
    downloaded
raises: |
  * :class:`.CheckbDirectiveError`: if mandatory parameters are missing or incorrect parameter
    values were provided
  * :class:`.CheckbRemoteError`: if downloading failed
version_added: 0.4
"""

EXAMPLES = """
Rpmlint needs to download a specific build from Koji, all supported architectures including
src.rpm::

  - name: download rpms from koji
    koji:
        action: download
        koji_build: ${koji_build}
        arch: all
        src: True

Depcheck needs to download all builds in a specific Koji tag for the current
architecture::

  - name: download koji tag
    koji:
        action: download_tag
        koji_tag: ${koji_tag}
        arch: ${arch}
        target_dir: ${workdir}/downloaded_tag/

Abicheck downloads both current build and latest stable build. It checks all supported binary
arches, but doesn't need ``noarch``::

  - name: download latest stable rpms for the package
    koji:
        action: download_latest_stable
        koji_build: ${koji_build}
        arch: all
        arch_exclude: noarch
        debuginfo: True
        target_dir: ${workdir}/stable

  - name: download rpms for the tested build
    koji:
        action: download
        koji_build: ${koji_build}
        arch: all
        arch_exclude: noarch
        debuginfo: True
        target_dir: ${workdir}/update

"""

directive_class = 'KojiDirective'


class KojiDirective(BaseDirective):

    def __init__(self, koji_session=None):
        super(KojiDirective, self).__init__()
        if koji_session is None:
            self.koji = KojiClient()
        else:
            self.koji = koji_session

    def process(self, params, arg_data):
        # process params
        valid_actions = ['download', 'download_tag', 'download_latest_stable']
        action = params['action']
        if action not in valid_actions:
            raise exc.CheckbDirectiveError('%s is not a valid action for koji '
                                              'directive' % action)

        if 'arch' not in params or 'target_dir' not in params:
            detected_args = ', '.join(params.keys())
            raise exc.CheckbDirectiveError(
                "The koji directive requires 'arch' and 'target_dir' as an "
                "argument. Detected arguments: %s" % detected_args)

        # convert str to list
        for param in ('arch', 'arch_exclude'):
            if param in params and isinstance(params[param], basestring):
                params[param] = [params[param]]

        arches = list(params['arch'])
        if arches and ('all' not in arches) and ('noarch' not in arches):
            arches.append('noarch')

        arch_exclude = params.get('arch_exclude', [])
        debuginfo = params.get('debuginfo', False)
        src = params.get('src', False)
        build_log = params.get('build_log', False)

        target_dir = params['target_dir']
        file_utils.makedirs(target_dir)

        # download files
        output_data = {}

        if action == 'download':
            if 'koji_build' not in params:
                detected_args = ', '.join(params.keys())
                raise exc.CheckbDirectiveError(
                    "The koji directive requires 'koji_build' for the 'download' "
                    "action. Detected arguments: %s" % detected_args)

            nvr = rpm_utils.rpmformat(params['koji_build'], 'nvr')

            output_data['downloaded_rpms'] = self.koji.get_nvr_rpms(
                nvr, target_dir, arches=arches, arch_exclude=arch_exclude,
                debuginfo=debuginfo, src=src)

        elif action == 'download_tag':
            if 'koji_tag' not in params:
                detected_args = ', '.join(params.keys())
                raise exc.CheckbDirectiveError(
                    "The koji directive requires 'koji_tag' for the 'download_tag' "
                    "action. Detected arguments: %s" % detected_args)

            koji_tag = params['koji_tag']

            output_data['downloaded_rpms'] = self.koji.get_tagged_rpms(
                koji_tag, target_dir, arches=arches, arch_exclude=arch_exclude,
                debuginfo=debuginfo, src=src)

        elif action == 'download_latest_stable':
            if 'koji_build' not in params:
                detected_args = ', '.join(params.keys())
                raise exc.CheckbDirectiveError(
                    "The koji directive requires 'koji_build' for the 'download_latest_stable' "
                    "action. Detected arguments: %s" % detected_args)

            name = rpm_utils.rpmformat(params['koji_build'], 'n')
            disttag = rpm_utils.get_dist_tag(params['koji_build'])
            # we need to do 'fc22' -> 'f22' conversion
            tag = disttag.replace('c', '')

            # first we need to check updates tag and if that fails, the latest
            # stable nvr is in the base repo
            tags = ['%s-updates' % tag, tag]
            nvr = self.koji.latest_by_tag(tags, name)

            if not nvr:
                log.info("There's no previous stable build for %s, skipping.",
                         params['koji_build'])
                assert output_data == {}
                return output_data

            output_data['downloaded_rpms'] = self.koji.get_nvr_rpms(
                nvr, target_dir, arch_exclude=arch_exclude,
                arches=arches, debuginfo=debuginfo, src=src)

        # download build.log if requested
        if build_log:
            if action in ('download', 'download_latest_stable'):
                ret_log = self.koji.get_build_log(
                        nvr, target_dir, arches=arches, arch_exclude=arch_exclude)
                output_data['downloaded_logs'] = ret_log['ok']
                output_data['log_errors'] = ret_log['error']
            else:
                log.warning("Downloading build logs is not supported for action '%s', ignoring.",
                            action)

        return output_data
