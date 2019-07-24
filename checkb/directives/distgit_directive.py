# -*- coding: utf-8 -*-
# Copyright 2009-2015, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

from __future__ import absolute_import

import os.path

from checkb.directives import BaseDirective
from checkb import file_utils, python_utils
from checkb.ext.fedora import rpm_utils, yumrepoinfo
import checkb.exceptions as exc
from checkb.logger import log


DOCUMENTATION = """
module: distgit_directive
short_description: download files from distgit
description: |
  Download files from Fedora package repository (usually called 'distgit') hosted at
  http://pkgs.fedoraproject.org/. Any files hosted at that repository can be downloaded for a
  chosen package.
parameters:
  package:
    required: true
    description: |
      Name of a package. You need to provide either ``package`` or ``nvr`` parameter.
      Example: ``xchat``
    type: str
  nvr:
    required: true
    description: |
      N(E)VR of the package build. If you input this, then the ``package``, ``gitref`` and
      ``namespace`` parameters will be automatically filled out (by parsing package name, dist tag,
      and using ``rpms`` namespace, respectively), but you can still override those if needed. You
      need to provide either ``package`` or ``nvr`` parameter.
      Example: ``xchat-2.8.8-32.fc25``
    type: str
  gitref:
    required: false
    description: |
      A git ref to check out.  May be a branch, tag, or commit hash.
      Example: ``f24`` or ``04164165a840405e6bb5acc54a51e22346d84e0d``
    type: str
    default: master
  namespace:
    required: false
    description: |
      dist-git namespace to use when constructing the url to clone.
      Example: ``modules``, ``rpms`` or ``docker``
    type: str
    default: rpms
  path:
    required: true
    description: |
      files (directories not supported at the moment) to be downloaded from distgit.
      Example: ``[xchat.spec]``
    type: list of str
  localpath:
    required: false
    description: |
      a local path of downloaded file. If not provided, path from distgit will be used.
      Example: ``[specs/xchat.spec]``
    type: list of str
  target_dir:
    required: true
    description: directory into which to download files
    type: str
  baseurl:
    required: false
    description: |
      The baseurl to use for dist-git.  Defaults to Fedora's production instance.
      Example: ``https://src.stg.fedoraproject.org``
    type: str
    default: https://src.fedoraproject.org
  ignore_missing:
    required: false
    description: |
      Ignore 404 error when requested files are missing in distgit
    type: bool
    default: False
returns: |
  A dictionary containing following items:

  * `downloaded_files`: (list of str) a list of local filenames of the downloaded
    files
raises: |
  * :class:`.CheckbRemoteError`: if downloading failed
  * :class:`.CheckbValueError`: if path and localpath are not lists or are not of the same
    length
  * :class:`.CheckbDirectiveError`: if package or path is missing
version_added: 0.3.16
"""

EXAMPLES = """
A task needs to download a spec file and httpd configuration check to run a check
on those files::

  - name: download spec file and httpd conf
    distgit:
      nvr: ${koji_build}
      path:
          - yourls.spec
          - yourls-httpd.conf
      localpath:
          - download/yourls_downloaded.spec
          - download/yourls-httpd_downloaded.conf

You can make some of that configuration static and not depend on NVR parsing, if you need so::

  - name: download spec file and httpd conf
    distgit:
      package: yourls
      gitref: f22
      path:
          - yourls.spec
          - yourls-httpd.conf
      localpath:
          - download/yourls_downloaded.spec
          - download/yourls-httpd_downloaded.conf
"""

directive_class = 'DistGitDirective'

BASEURL = 'https://src.fedoraproject.org'
URL_FMT = '{baseurl}/{namespace}/{package}/raw/{gitref}/f/{path}'


class DistGitDirective(BaseDirective):
    def __init__(self):
        super(DistGitDirective, self).__init__()

    def process(self, params, arg_data):
        if ('package' not in params and 'nvr' not in params) or 'path' not in params \
            or 'target_dir' not in params:
            detected_args = ', '.join(params.keys())
            raise exc.CheckbDirectiveError(
                "The distgit directive requires 'package' (or 'nvr') and 'path' and 'target_dir' arguments."
                "Detected arguments: %s" % detected_args)

        package = None
        gitref = None
        namespace = None

        if 'nvr' in params:
            nvr = params['nvr']
            package = rpm_utils.rpmformat(nvr, fmt='n')
            gitref = rpm_utils.get_dist_tag(nvr).replace('c', '')
            rawhide_tag = yumrepoinfo.YumRepoInfo(resolve_baseurl=False).get(
                'rawhide', 'tag')
            if gitref == rawhide_tag:
                gitref = 'master'
            namespace = 'rpms'

        # Assign defaults
        package = params.get('package', package)
        gitref = params.get('gitref', gitref or 'master')
        namespace = params.get('namespace', namespace or 'rpms')
        baseurl = params.get('baseurl', BASEURL)
        target_dir = params['target_dir']
        ignore_missing = params.get('ignore_missing', False)

        if not python_utils.iterable(params['path']):
            raise exc.CheckbValueError("Incorrect value type of the 'path' argument: "
                                          "%s" % type(params['path']))

        target_path = params['path']
        output_data = {}

        if 'localpath' in params:
            if not python_utils.iterable(params['localpath']):
                raise exc.CheckbValueError("Incorrect value type of the 'localpath' argument: "
                                              "%s" % type(params['path']))

            if not len(params['path']) == len(params['localpath']):
                raise exc.CheckbValueError('path and localpath lists must be of the same '
                                              'length.')

            target_path = params['localpath']

        format_fields = {
            'package': package,
            'gitref': gitref,
            'namespace': namespace,
            'baseurl': baseurl,
        }
        output_data['downloaded_files'] = []
        for path, localpath in zip(params['path'], target_path):
            localpath = os.path.join(target_dir, localpath)
            file_utils.makedirs(os.path.dirname(localpath))
            url = URL_FMT.format(path=path, **format_fields)
            try:
                output_data['downloaded_files'].append(
                    file_utils.download(url, '.', localpath)
                )
            except exc.CheckbRemoteError as e:
                if e.errno == 404 and ignore_missing:
                    log.debug('File not found, ignoring: %s', url)
                else:
                    raise e


        return output_data
