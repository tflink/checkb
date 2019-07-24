# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing
from __future__ import absolute_import

DOCUMENTATION = """
module: createrepo_directive
short_description: create a YUM repository from RPM packages using createrepo_c
description: |
  Take a directory containing RPM packages and run ``createrepo_c`` command on
  it, which creates YUM repository metadata inside of it.
parameters:
  repodir:
    required: true
    description: absolute or relative path to the directory containing RPM files
      (the task directory is considered the current working directory)
    type: str
returns: |
  Standard output (``string``) of the ``createrepo_c`` process.
raises: |
  * :class:`.CheckbDirectiveError`: if there's any output on standard error
    stream of the ``createrepo_c`` process
version_added: 0.4
"""

EXAMPLES = """
First, download all required RPMs, then create a YUM repository in that
directory::

  - name: download koji tag
    koji:
        action: download_tag
        koji_tag: ${koji_tag}
        arch: ${arch}
        target_dir: ${workdir}/downloaded_tag/

  - name: create YUM repository metadata
    createrepo:
        repodir: ${workdir}/downloaded_tag/
"""

import subprocess as sub
from checkb.directives import BaseDirective
from checkb.logger import log
from checkb.exceptions import CheckbDirectiveError

directive_class = 'CreaterepoDirective'

class CreaterepoDirective(BaseDirective):

    def process(self, params, arg_data):
        repodir = params['repodir']

        log.info('running createrepo_c on %s', repodir)

        p = sub.Popen(['createrepo_c', repodir], stdout=sub.PIPE, stderr=sub.PIPE)

        output, errors = p.communicate()

        if p.returncode:
            raise CheckbDirectiveError(errors)

        log.debug(output)

        return output
