# -*- coding: utf-8 -*-
# Copyright 2009-2016, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

from __future__ import absolute_import


DOCUMENTATION = """
module: create_report_directive
short_description: generate a report of task results
description: |
  Generate report of task results in HTML format to given path.

parameters:
  results:
    required: true
    description: |
      A string containing task results in the ResultYAML format. You must use either ``results``
      or ``file`` parameter (exactly one).
    type: str
  file:
    required: true
    description: |
      A path to a file containing the task results in the ResultYAML format. You must use either
      ``results`` or ``file`` parameter (exactly one).
    type: str
  artifactsdir:
    required: true
    description: |
      A path to the artifacts directory.
    type: str
  path:
    required: false
    description: |
      A path and a filename of the generated HTML report. You should always use relative
      paths, and ``${artifactsdir}`` is considered to be the base directory. All missing
      directories will be created automatically. Example: ``reports/overview.html``
    type: str
    default: report.html
  template:
    required: false
    description: |
      A path to a template to be used to generate a report. By default, a
      standard checkb report template will be used.
      Example: ``/tmp/report.j2``
    type: str
raises: |
  * :class:`.CheckbDirectiveError`: if both ``results`` and ``file`` parameters are used; or if
    their contents is not in a valid YAML format; or if ``path`` cannot be created.
version_added: 0.4
"""

EXAMPLES = """
These two actions first run ``run_rpmlint.py`` and export its YAML output to
``${rpmlint_output}``, and then feed this YAML output to the ``create_report``
directive::

    - name: run rpmlint on downloaded rpms
      python:
          file: run_rpmlint.py
          callable: run
          workdir: ${workdir}
      export: rpmlint_output

    - name: make html report of the results
      create_report:
          results: ${rpmlint_output}

This example shows using the ``file`` parameter. The ``randomtest`` produces a ``testoutput.yml``
file containing results in the YAML format, that the ``create_report`` directive then uses::

    - name: run randomtest on downloaded rpms
      shell:
          - bash ./randomtest.sh --outfile=${workdir}/testoutput.yml

    - name: make html report of the results
      create_report:
          file: ${workdir}/testoutput.yml
"""

import os

import jinja2

from checkb.directives import BaseDirective

from checkb import check
from checkb import file_utils
from checkb import config
from checkb.exceptions import CheckbDirectiveError, CheckbValueError
from checkb.logger import log
import checkb.exceptions as exc


directive_class = 'CreateReportDirective'


class CreateReportDirective(BaseDirective):

    def process(self, params, arg_data):

        if 'file' in params and 'results' in params:
            raise CheckbDirectiveError("Either `file` or `results` can be used, not both.")

        if 'artifactsdir' not in params:
            detected_args = ', '.join(params.keys())
            raise exc.CheckbDirectiveError(
                "The directive requires 'artifactsdir' as an "
                "argument. Detected arguments: %s" % detected_args)
        artifactsdir = params['artifactsdir']

        try:
            if params.get('file', None):
                with open(params['file']) as resultfile:
                    params['results'] = resultfile.read()

            check_details = check.import_YAML(params['results'])
            log.debug("YAML output parsed OK.")
        except (CheckbValueError, IOError) as e:
            raise CheckbDirectiveError("Failed to load results: %s" % e.message)

        log.debug('Generating report of %s results...', len(check_details))

        results = []
        for detail in check_details:
            results.append({
                'checkname': detail.checkname,
                'outcome': detail.outcome,
                'note': detail.note or '---',
                'item': detail.item,
                'type': detail.report_type,
                'artifact': os.path.basename(detail.artifact) if detail.artifact else None,
            })

        if 'path' in params:
            report_fname = os.path.join(artifactsdir, params['path'])
        else:
            report_fname = os.path.join(artifactsdir, 'report.html')

        if 'template' in params:
            template_fname = params['template']
        else:
            template_fname = os.path.join(config.get_config()._data_dir,
                                          'report_templates/html.j2')

        try:
            file_utils.makedirs(os.path.dirname(report_fname))
        except OSError as e:
            raise CheckbDirectiveError(e)

        with open(template_fname) as f_template:
            with open(report_fname, 'w') as f_report:
                template = jinja2.Template(f_template.read())
                report = template.render(results=results,
                                         artifactsdir=artifactsdir)
                f_report.write(report)

        log.info('Report generated in: %s', os.path.abspath(report_fname))
