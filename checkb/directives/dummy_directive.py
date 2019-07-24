# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing
from __future__ import absolute_import

DOCUMENTATION = """
module: dummy_directive
short_description: test how directives work
description: |
  This is just what it sounds like - a directive that doesn't do anything other
  than (optionally) return a message or raise an error. It is primarially meant
  for testing the runner or as a placeholder while writing new tasks. Or you can
  play with it to learn the directive basics.
parameters:
  result:
    required: true
    description: arbitrary string. If it equals ``FAIL`` (case ignored), then
      the directive raises an error.
    type: str
  msg:
    required: false
    description: arbitrary string. If it is present, it is returned.
    type: anything
returns: |
  Either ``msg``, if it was provided, or ``None``.
raises: |
  * :class:`.CheckbDirectiveError`: if ``result="FAIL"`` (case ignored)
version_added: 0.4
"""

EXAMPLES = """
This simply returns ``msg`` that was provided::

 - name: return Koji build (NVR)
   dummy:
     result: PASS
     msg: ${koji_build}

This raises an error, regardless of whether or what was provided in ``msg``::

 - name: raise an error
   dummy:
     result: FAIL
"""


from checkb.directives import BaseDirective
from checkb.exceptions import CheckbDirectiveError

directive_class = 'DummyDirective'

class DummyDirective(BaseDirective):

    def process(self, params, arg_data):
        expected_result = params['result']

        if expected_result.lower() == 'fail':
            raise CheckbDirectiveError("This is a dummy directive and "
                                          "configured to fail")

        if 'msg' in params:
            return params['msg']
