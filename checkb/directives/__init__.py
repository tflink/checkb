# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing
from __future__ import absolute_import

'''Directives are standalone code snippets which act as helper functions when
the task needs to achieve something inside the task formula file. They allow
to prepare the environment for running the task, or to do something with the
task output. The benefit of directives is that they share useful code between
tasks, so that the tasks don't have to include a lot of commonly needed
functionality and can rely on directives to do that instead.

Examples include downloading RPMs from Koji, creating Yum repositories,
reporting results to ResultsDB, or running an arbitrary python script (which
is also used for the main task script execution).

Each directive must inherit from :class:`BaseDirective` and implement its
:meth:`~BaseDirective.process`` method. It also needs to provide a global
variable :data:`directive_class` which specifies this child directive class name.

The documentation of the directives is done through two global variables -
``DOCUMENTATION`` and ``EXAMPLES``. In this file, you'll find a template for
both these attributes.'''

DOCUMENTATION = """
# This is structured as a YAML document. If a key doesn't apply to your
# directive, simply remove it. You can use reST markup in all string fields.
# If you need to include `:` or newlines in a string, start with with a `|`
# symbol and a newline, as shown below.
module: directive_name (same as the file name)
short_description: one sentence describing the purpose of the directive
description: |
  Full description of the directive. You can use inline markup in reST
  format, like **bold** and `hyperlinks <http://example.org>`_. New paragraphs
  are separated by a blank line.

  reST block markup is supported as well, simply ensure that your block is
  indented correctly. Code markup example::

    This is a preformatted
    code block

  Add notes like this:

  .. note:: This sentence will get highlighted and framed in a block.
parameters:
  # One or more options using the following format.
  parameter_name:
    required: true
    description: |
      Description of the option, again with some ``values`` formatting.

      Blank lines force a line break.
    type: parameter type, e.g. `str` or `list of str`
    default: a default value, if applicable; otherwise remove the line
    choices: [choices, separated, by, commas, if, applicable]
returns: |
  Describe the return value of this directive. Example:

  ``None``
raises: |
  Describe which exceptions are raised in which circumstances. Example:

  * :class:`.CheckbDirectiveError`: if ``file`` can't be read
  * :class:`.CheckbRemoteError`: when RPMs can't be fetched from the server
version_added: 0.4
"""

EXAMPLES = """
Show real-world examples how to use the directive. Describe what's happening.
Use multiple examples if appropriate. Example:

Download all RPMs from ``f20-updates-pending`` tag to
``${workdir}/tagdownload/``::

 - name: download f20-updates-pending to tagdownload
   koji:
     action: download_tag
     tag: f20-updates-pending
     target_dir: ${workdir}/tagdownload
"""

directive_class = 'BaseDirective'


class BaseDirective(object):
    '''The interface definition for all directive classes. They should inherit this and implement
    required methods.'''

    def __init__(self):
        pass

    def process(self, params, arg_data):
        '''Main entry point for the directive. Executes the directive.

        :param dict params: all parameters received as an input for this directive. They should
            reflect what you have documented in ``parameters`` key in ``DOCUMENTATION`` global
            variable. You have to validate them manually and you should raise
            ``.CheckbDirectiveError`` for any missing or invalid input parameter (and also
            document this behavior in ``raises`` key in ``DOCUMENTATION``).
        :param dict arg_data: processed runner cli arguments (see :func:`main.process_args`)
            enriched with additional runtime variables like ``workdir`` or ``checkname`` (see
            :class:`.Executor`)
        '''
        raise NotImplementedError
