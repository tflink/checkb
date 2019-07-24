# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

from __future__ import absolute_import

from checkb.python_utils import basestring

DOCUMENTATION = """
module: yumrepoinfo_directive
short_description: translate Koji tags into YUM repository URLs
description: |
  Translate a Koji tag into a set of YUM repositories. This is useful when you
  want to work with YUM metadata for a specific Fedora repository, but you only
  know its Koji tag.
parameters:
  koji_tag:
    required: true
    description: |
      name of the Koji tag, e.g. ``f20``, ``f20-updates``,
      ``f20-updates-testing``, or ``rawhide``.

      If the tag ends with ``-pending`` suffix, this suffix is stripped (because
      pending tags are not real repositories), and the resulting tag is used.
    type: str
  arch:
    required: true
    description: an architecure (or a list of architectures). All "meta architectures"
      like ``all``, ``src`` and ``noarch`` are ignored, "real
      architectures" are expected there instead (e.g. ``x86_64`` or ``i386``).
    type: str or list of str
returns: |
    A dictionary of dictionaries. Main key is ``koji_tag`` with value of
    dictionary that contains ``arch`` as key and URL for the respective
    repository is its value.

    If the repository in question has some parent repositories (e.g.
    ``f20-updates`` is a child of ``f20``), all its parents names and their
    repository URLs are returned in the dictionary as well as additional keys.
    Example::

        {'f20': {'x86_64': 'http://...',
                 'i386': 'http://...'},
         'f20-updates': {'x86_64': 'http://...',
                         'i386': 'http://...'}}
raises: |
  * :class:`.CheckbDirectiveError`: if there are zero "real architectures"
    inside ``arch`` or when ``koji_tag`` is not found among known repositories.
version_added: 0.4
"""

EXAMPLES = """
For a koji tag received from the command line, get a list of its YUM
repositories and save it to a variable::

    - name: get yum repos
      yumrepoinfo:
          koji_tag: ${koji_tag}
          arch: ${arch}
      export: yumrepos

Now you can pass ``${yumrepos}`` dictionary to your python script and run your
check::

    - name: run my check
      python:
          file: my_check.py
          callable: run
          repos: ${yumrepos}
          arch: ${arch}
      export: my_check_output
"""

from checkb.arch_utils import Arches
from checkb.directives import BaseDirective
from checkb.exceptions import CheckbDirectiveError
from checkb.logger import log
from checkb.ext.fedora import yumrepoinfo


directive_class = 'YumrepoinfoDirective'

class YumrepoinfoDirective(BaseDirective):

    def __init__(self, repoinfo=None, filelist=None):
        """
        :param repoinfo: if provided, get_yumrepoinfo() call is omitted and
                         this info is used instead (for testing mainly)
        :param filelist: list of config files, default config file is used
                         if None (for testing mainly)
        """
        self.repoinfo = repoinfo
        self.filelist = filelist

    def run_yumrepoinfo(self, arch, koji_tag):
        """Get yum repoinfo for given arch and koji tag"""

        output = {}

        if self.repoinfo is None:
            self.repoinfo = yumrepoinfo.get_yumrepoinfo(arch, self.filelist)

        if koji_tag.endswith('-pending'):
           koji_tag = koji_tag[:-len('-pending')]

        if koji_tag == 'rawhide':
            koji_tag = self.repoinfo.repo('rawhide')['tag']

        while koji_tag:
            repo = self.repoinfo.repo_by_tag(koji_tag)
            if repo is None:
                raise CheckbDirectiveError('Repo with tag'\
                        '%r not found.' % koji_tag)

            output[repo['name']] = repo['url']
            koji_tag = repo['parent']

        log.debug("Found %s repos for %s: %r" % (len(output),
                  koji_tag, output))
        return output

    def process(self, params, arg_data):

        if 'koji_tag' not in params or 'arch' not in params:
            raise CheckbDirectiveError("The yumrepoinfo directive requires "
                                          "koji_tag and arch arguments.")

        # convert str to list
        if isinstance(params['arch'], basestring):
            params['arch'] = [params['arch']]

        arches = params['arch']
        processed_arches = [arch for arch in arches if arch in Arches.base]

        if len(processed_arches) == 0:
            raise CheckbDirectiveError("No valid yumrepo arches supplied to "
                                          "yumrepoinfo directive. Received %r"
                                       % arches)

        # create output in format:
        # {'koji_tag' : {'arch' : 'URL'}}
        output = {}
        for arch in processed_arches:
            arch_output = self.run_yumrepoinfo(arch, params["koji_tag"])
            self.repoinfo = None
            for tag in arch_output:
                output[tag] = output.get(tag, {})
                output[tag][arch] = arch_output[tag]

        return output
