# -*- coding: utf-8 -*-
# Copyright 2009-2016, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

from __future__ import absolute_import

from checkb.directives import BaseDirective
from checkb.logger import log
from checkb.exceptions import CheckbDirectiveError
import checkb.ext.fedora.bodhi_utils as bodhi
from checkb.ext.fedora.koji_utils import KojiClient
from checkb.python_utils import basestring
from checkb import config
from checkb import exceptions as exc

DOCUMENTATION = """
module: bodhi_directive
short_description: download updates from Bodhi
description: |
  The bodhi directive interfaces with `Bodhi`_ to facilitate various actions.
  At the moment, the only action supported is downloading updates (i.e. all RPMs
  from all builds related to a specific update).

  .. _Bodhi: https://bodhi.fedoraproject.org
parameters:
  action:
    required: true
    description: specify action type. The only action available at the moment
      is ``download``.
    type: str
  update_id:
    required: true
    description: Bodhi update ID to download, e.g. ``FEDORA-2014-7485``.
    type: str
  arch:
    required: true
    description: |
      an architecture (or a list of architectures) for which to download RPMs.

      Note: ``noarch`` RPMs are always automatically downloaded even when not
      requested, unless ``arch=[]`` and ``src=True``.
    type: str or list of str
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

  * ``downloaded_rpms``: (list of str) a list of local filenames of the
    downloaded RPMs
raises: |
  * :class:`.CheckbDirectiveError`: if no update with ``update_id`` has been
    found
  * :class:`.CheckbRemoteError`: if downloading failed
  * :class:`.CheckbValueError`: if ``arch=[]`` and ``src=False``, therefore
    there is nothing to download
version_added: 0.4
"""

EXAMPLES = """
Download a Bodhi update provided on the command line and then check it with
rpmlint::

    - name: download update from Bodhi
      bodhi:
        action: download
        update_id: ${update_id}
        arch: ${arch}

    - name: run rpmlint on downloaded rpms
      python:
          file: run_rpmlint.py
          callable: run
          workdir: ${workdir}
      export: rpmlint_output
"""

directive_class = 'BodhiDirective'


class BodhiDirective(BaseDirective):

    def __init__(self, bodhi_api=None, koji_session=None):

        if bodhi_api:
            self.bodhi_api = bodhi_api
        else:
            self.bodhi_api = bodhi.BodhiUtils()

        if koji_session:
            self.koji_session = koji_session
        else:
            self.koji_session = KojiClient()

    def action_download(self, updateid, arches, src, workdir):

        res = self.bodhi_api.get_update(updateid)

        if res is None:
            raise CheckbDirectiveError("Update with ID '%s' wasn't found" % updateid)

        nvrs = [build['nvr'] for build in res['builds']]

        downloaded_rpms = []

        for nvr in nvrs:
            res = self.koji_session.get_nvr_rpms(nvr, workdir, arches, src=src)
            downloaded_rpms.extend(res)

        return downloaded_rpms

    def process(self, params, arg_data):
        output_data = {}
        valid_actions = ['download']
        action = params.get('action', None)

        if action not in valid_actions:
            raise CheckbDirectiveError('%s is not a valid command for bodhi directive'
                                       % action)

        if 'arch' not in params or 'target_dir' not in params:
            detected_args = ', '.join(params.keys())
            raise exc.CheckbDirectiveError(
                "The bodhi directive requires 'arch' and 'target_dir' as an "
                "argument. Detected arguments: %s" % detected_args)

        # convert str to list
        if isinstance(params['arch'], basestring):
            params['arch'] = [params['arch']]

        if action == 'download':
            if 'update_id' not in params or 'arch' not in params:
                detected_args = ', '.join(params.keys())
                raise CheckbDirectiveError(
                    "The bodhi directive 'download' requires both 'update_id' and "
                    "'arch' arguments. Detected arguments: %s" % detected_args)

            target_dir = params['target_dir']
            updateid = params['update_id']
            if 'all' in params['arch']:
                arches = config.get_config().supported_arches + ['noarch']
            else:
                arches = params['arch']
            if arches and ('noarch' not in arches):
                arches.append('noarch')

            src = params.get('src', False)

            log.info("getting rpms for update %s (%s) and downloading to %s",
                     updateid, arches, target_dir)

            output_data['downloaded_rpms'] = self.action_download(updateid, arches, src, target_dir)

        return output_data
