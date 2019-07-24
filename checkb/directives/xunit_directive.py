# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

from __future__ import absolute_import

import xunitparser

from checkb.directives import BaseDirective
from checkb.exceptions import CheckbDirectiveError
from checkb.check import CheckDetail, export_YAML

DOCUMENTATION = """
module: xunit_directive
short_description: parse an xUnit XML file into the ResultYAML format
description: |
  Parse test ouput in XML xUnit format and generate :doc:`ResultYAML </resultyaml>`.

  .. note::
    The input xUnit file is set as an artifact in the output ResultYAML result, therefore it's
    recommended that you place it inside ``${artifactsdir}``.
parameters:
  item:
    required: true
    description: Item of the task, as provided by Checkb runner
    type: str
  type:
    required: true
    description: Item type of the task, as provided by Checkb runner
    type: str
  checkname:
    required: true
    description: Test case identification
    type: str
  file:
    required: true
    description: xUnit XML file path to be parsed, either absolute or relative to task directory
    type: str
  aggregation:
    required: false
    description: |
      type of result aggregation: ``allpass`` will aggregate testcases into a single result with
      outcome ``PASSED`` if all testcases passed, otherwise ``FAILED``. ``none`` means no
      aggregation and all testcases will be reported as separate results.
    type: str
    default: allpass
    choices: [allpass, none]
returns: |
  check result(s) in the ResultYAML format
raises: |
  * :class:`.CheckbDirectiveError`: if mandatory parameters are missing or incorrect parameter
    values were provided
version_added: 0.4.14
"""

EXAMPLES = """
This example parses xUnit XML file located in ``${artifactsdir}``, generates ResultYAML from it and
exports it to a variable which is then passed to ``resultsdb`` directive::

  - name: parse xunit output
    xunit:
        file: ${artifactsdir}/xunit_output.xml
    export: resultyaml

  - name: report results to resultsdb
    resultsdb:
        results: ${resultyaml}
"""

directive_class = 'XunitDirective'


# https://github.com/laurentb/xunitparser/issues/10
xunitparser.TestSuite._cleanup = False


class XunitDirective(BaseDirective):

    aggregations = ['none', 'allpass']

    def process(self, params, arg_data):
        for param in ['item', 'type', 'checkname', 'file']:
            if param not in params.keys():
                raise CheckbDirectiveError('Mandatory parameter missing: %s' % param)
        item = params['item']
        itemtype = params['type']
        checkname = params['checkname']
        xunitfile = params['file']

        aggregation = params.get('aggregation', 'allpass')

        if aggregation not in self.aggregations:
            raise CheckbDirectiveError(
                "Aggregation '%s' is not one of: %s" % (aggregation, ', '.join(self.aggregations)))

        with open(xunitfile) as xmlfile:
            testsuite, testresult = xunitparser.parse(xmlfile)

        if aggregation == 'none':
            details = []
            for tc in testsuite:
                outcome = 'PASSED' if tc.good else 'FAILED'
                details.append(CheckDetail(item=item,
                                           checkname="%s.%s" % (checkname,
                                                                tc.methodname),
                                           report_type=itemtype,
                                           outcome=outcome,
                                           artifact=xunitfile))
            return export_YAML(details)

        elif aggregation == 'allpass':
            passed = len([tc for tc in testsuite if tc.good])
            failed = len([tc for tc in testsuite if not tc.good])
            final_outcome = 'PASSED' if failed == 0 else 'FAILED'
            note = CheckDetail.create_multi_item_summary(['PASSED'] * passed + ['FAILED'] * failed)

            return export_YAML(CheckDetail(item=item,
                                           report_type=itemtype,
                                           outcome=final_outcome,
                                           checkname=checkname,
                                           note=note,
                                           artifact=xunitfile))

        else:
            assert False, "This should never happen, aggregation is %r" % aggregation
