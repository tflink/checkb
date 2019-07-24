# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

from __future__ import absolute_import

DOCUMENTATION = """
module: exitcode_directive
short_description: set runtask exit code based on last or worst test outcome
description: |
  This directives takes YAML specified by key ``result_last`` or ``result_worst`` (keys are
  mutually exclusive), and generates returncode based on last or worst YAML outcome.
  If YAML is empty, exitcode is set to SUCCESS.

  If task formula contains multiple usages of exitcode directive, worst exitcode is returned by
  runtask.

  Input for directive is supposed to be in a :doc:`/resultyaml`. The easiest way to create it
  is to use :class:`.CheckDetail` objects to construct your result (or results), and then generate
  the YAML output with :func:`~.check.export_YAML`.
  Read more in :doc:`/writingtasks`.

parameters:
  result_last:
    required: true
    description: YAML output, last outcome is used. ``result_worst`` cannot be specified together
      with this one.
    type: str
  result_worst:
    required: true
    description: YAML output, worst outcome is used. ``result_last`` cannot be specified together
      with this one.
    type: str
returns: |
  :int: Returncode based on YAML last or worst outcome. Success is ``0``, failure is ``100``.
raises: |
  * :class:`.CheckbDirectiveError`: when there's not exactly one of parameters ``result_last``
    or ``result_last`` present
  * :class:`.CheckbValueError`: when YAML input cannot be parsed
version_added: 0.3.18
"""

EXAMPLES = """
Run a check returning multiple results and make ``runtask`` fail if any of the results is failed::

  - name: run my check and return YAML
    python:
        file: my_check.py
        callable: run
    export: results

  - name: set runtask exit code according to the worst result in YAML
    exitcode:
        result_worst: ${results}

Run a check that returns multiple results and one "overall" result (at the end) which is computed
according check's internal logic. Then make ``runtask`` fail if the overall result failed::

  - name: run my check and return YAML
    python:
        file: my_check.py
        callable: run
    export: results

  - name: set runtask exit code according to the last (overall) result in YAML
    exitcode:
        result_last: ${results}
"""

from checkb.directives import BaseDirective
from checkb.exceptions import CheckbDirectiveError
from checkb.logger import log
from checkb import check


# exitcode for PASSED and INFO outcome
SUCCESS = 0

# exitcode for other outcomes
FAILURE = 100

directive_class = 'ExitcodeDirective'


class ExitcodeDirective(BaseDirective):

    def process(self, params, arg_data):
        # keys 'result_worst' and 'result_last' must be mutually exclusive
        if ('result_worst' in params) == ('result_last' in params):
            raise CheckbDirectiveError("The exitcode directive requires exactly one of keys "
                                          "'result_worst' or 'result_last'.")

        if 'result_worst' in params:
            details = check.import_YAML(params['result_worst'])
            code = SUCCESS
            for detail in details:
                if detail.outcome not in ['PASSED', 'INFO']:
                    code = FAILURE

            log.debug("Returning exitcode %d" % code)
            return code

        elif 'result_last' in params:
            details = check.import_YAML(params['result_last'])
            if details and details[-1].outcome not in ['PASSED', 'INFO']:

                log.debug("Returning exitcode %d" % FAILURE)
                return FAILURE
            else:
                log.debug("Returning exitcode %d" % SUCCESS)
                return SUCCESS

        else:
            assert False, "This should never occur"
