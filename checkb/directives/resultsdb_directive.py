# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

from __future__ import absolute_import

import os
import configparser
import pprint

from checkb.directives import BaseDirective
from checkb import check
from checkb import config
from checkb.exceptions import CheckbDirectiveError, CheckbValueError
from checkb.logger import log
import resultsdb_api

DOCUMENTATION = """
module: resultsdb_directive
short_description: send task results to ResultsDB or check ResultYAML format
  correctness
description: |
  Send check output to `ResultsDB <https://fedoraproject.org/wiki/ResultsDB>`_.

  If reporting to ResultsDB is disabled in the config (``report_to_resultsdb``
  option, disabled by default for the development profile), the directive at
  least checks whether the check output is in valid :doc:`/resultyaml` and logs the
  details that would have been reported. For this reason, it's useful to use
  resultsdb directive always, even when you don't have any ResultsDB server
  configured.

parameters:
  results:
    required: true
    description: Variable containing the results of the check in the ResultYAML
                 format. You must use either ``results`` or ``file`` parameter.
    type: str
  file:
    required: true
    description: Path to a file containing the results of the check in the
                 ResultYAML format.
                 You must use either ``results`` or ``file`` parameter.
    type: str
returns: |
  YAML formatted output as taken from input, enhanced with result-id's for each
  successfully stored result. The result-id information then can be used by
  other directives. If reporting to ResultsDB is disabled, the returned YAML
  does not contain this extra field.
raises: |
  * :class:`.CheckbDirectiveError`: if ``results`` is not in a valid YAML
    format, or when  ``item`` or ``type`` are missing in the YAML's result data,
    or when results are not allowed to be posted into a given namespace, or
    the namespace does not exist, or if both ``results`` and ``file`` parameters
    are used;
  * :class:`resultsdb_api.ResultsDBapiException`: for any errors coming from
    the ResultsDB server
version_added: 0.4
"""

EXAMPLES = """
These two actions first run ``run_rpmlint.py`` and export its YAML output to
``${rpmlint_output}``, and then feed this YAML output to ``resultsdb``
directive::

    - name: run rpmlint on downloaded rpms
      python:
          file: run_rpmlint.py
          callable: run
          workdir: ${workdir}
      export: rpmlint_output

    - name: report results to resultsdb
      resultsdb:
          results: ${rpmlint_output}

This example shows using the ``file`` parameter. The ``randomtest`` produces
a ``testoutput.yml`` file containing results in the YAML format, that the
``resultsdb`` directive then uses::

    - name: run randomtest on downloaded rpms
      shell:
          - bash ./randomtest.sh --outfile=${workdir}/testoutput.yml

    - name report results to resultsdb
      resultsdb:
          file: ${workdir}/testoutput.yml

If ResultsDB reporting is configured in the config file, it will get saved on
the ResultsDB server, otherwise only YAML compliance will get checked and some
summary will be printed out into the log, like this::

    [checkb:resultsdb_directive.py:143] 2014-06-24 13:55:27 INFO    YAML is OK.
    [checkb:resultsdb_directive.py:144] 2014-06-24 13:55:27 INFO    Reporting to ResultsDB is disabled.
    [checkb:resultsdb_directive.py:145] 2014-06-24 13:55:27 INFO    Once enabled, the following would be reported:
    [checkb:resultsdb_directive.py:146] 2014-06-24 13:55:27 INFO    <CheckDetail: {'_outcome': 'PASSED',
     'item': 'xchat-2.8.8-21.fc20.x86_64.rpm',
     'keyvals': {},
     'output': '<stripped out>',
     'report_type': 'koji_build',
     'summary': 'RPMLINT PASSED for xchat-2.8.8-21.fc20.x86_64.rpm'}>
    <CheckDetail: {'_outcome': 'PASSED',
     'item': 'xchat-tcl-2.8.8-21.fc20.x86_64.rpm',
     'keyvals': {},
     'output': '<stripped out>',
     'report_type': 'koji_build',
     'summary': 'RPMLINT PASSED for xchat-tcl-2.8.8-21.fc20.x86_64.rpm'}>
"""

directive_class = 'ResultsdbDirective'

def git_origin_url(taskdir):
    try:
        gitconfig_filename = os.path.join(taskdir, '.git/config')
        gitconfig = configparser.ConfigParser()
        gitconfig.read(gitconfig_filename)
        task_repo_url = gitconfig['remote "origin"']['url']
    except TypeError as e:
        log.exception(e)
        task_repo_url = None
    return task_repo_url



class ResultsdbDirective(BaseDirective):

    def __init__(self, resultsdb = None):
        self.resultsdb = resultsdb

        conf = config.get_config()
        self.masterurl = conf.checkb_master
        self.task_stepname = conf.buildbot_task_step
        self.execdb_server = "%s/jobs" % conf.execdb_server
        self.artifacts_baseurl = conf.artifacts_baseurl

        if self.resultsdb is None:
            self.resultsdb = resultsdb_api.ResultsDBapi(conf.resultsdb_server)

        self._ensured_testcases = []

    def ensure_testcase_exists(self, name):
        """ Make sure that the testcase exists in resultsdb, otherwise create
        the testcase using a dummy url as a reference

        :param str name: name of the testcase to check for
        """

        if name in self._ensured_testcases:
            return

        try:
            self.resultsdb.get_testcase(name)
            self._ensured_testcases.append(name)
            return
        except resultsdb_api.ResultsDBapiException as e:
            if not e.message.startswith('Testcase not found'):
                raise e

        # since the testcase doesn't exist, create it with a dummy value for url
        # it can be updated later when it's not blocking results reporting
        dummyurl = 'https://fedoraproject.org/wiki/Checkb/Tasks/%s' % name
        self.resultsdb.create_testcase(name, dummyurl)
        self._ensured_testcases.append(name)

    def create_resultsdb_group(self, uuid, name=None, refurl=None):
        """Prepare Group data for the Result

        :param str name: name of group to report against
        :param str uuid: UUID of the group (most probably provided by ExecDB)
        :param str refurl: url pointing to the execution overview.
           If set to None, ExecDB url is created from UUID
        :returns: dict containing the relevant group object data
        """

        url = "%s/%s" % (self.execdb_server, uuid)
        if refurl is not None:
            url = refurl

        group_data = {'uuid': uuid, 'ref_url': url}
        if name:
            group_data['description'] = name
        return group_data

    def get_artifact_path(self, artifactsdir, artifact):
        """Return the relative path of :attr str artifact: inside the
        :attr str artifactsdir:.
        :returns: relative path to the artifact file or None, if the file
                  does not exist, or is outside the artifactsdir.
        """
        artifactsdir = os.path.realpath(artifactsdir)
        if os.path.isabs(artifact):
            artifact_path = artifact
        else:
            artifact_path = os.path.join(artifactsdir, artifact)
        artifact_path = os.path.realpath(artifact_path)

        if not os.path.exists(artifact_path):
            log.warning('Artifact %r does not exist, ignoring' % artifact_path)
            return None
        elif not artifact_path.startswith(artifactsdir):
            log.warning('Artifact %r is placed outside of artifacts directory %r, ignoring',
                        artifact_path, artifactsdir)
            return None

        return os.path.relpath(artifact_path, start=artifactsdir)

    def check_namespace(self, checkname, arg_data):
        '''Determine if current task can submit results into its namespace. Return if it can,
        raise error if it can't.

        :param str checkname: full check name (including namespace prefix)
        :return: ``None``, it means task is allowed to post into the namespace
        :raise CheckbDirectiveError: if task is not allowed to post into the namespace
        '''
        conf_ns = config.load_namespaces_config()
        ns_repos = None

        # check if the namespace exists
        for ns in conf_ns['namespaces_safe']:
            if checkname.startswith(ns+'.'):
                log.debug('Namespace %s found in the safe namespaces.', ns)
                return

        for ns, repos in conf_ns['namespaces_whitelist'].items():
            if checkname.startswith(ns+'.'):
                log.debug('Namespace %s found in the namespace whitelist.', ns)
                ns_repos = repos
                break
        else:
            raise CheckbDirectiveError('No namespace for task %s exists.' % checkname)

        taskdir = os.path.dirname(os.path.abspath(arg_data['task']))
        task_repo_url = git_origin_url(taskdir)
        if not task_repo_url:
            raise CheckbDirectiveError("Could not find task's git remote 'origin' url"
                                          "in %s" % os.path.join(taskdir, '.git/config'))

        try:
            if not [ns_repo for ns_repo in ns_repos if task_repo_url.strip().startswith(ns_repo)]:
                log.warning('No namespace whitelist seems to match the task '
                            'repo URL: %s', task_repo_url)
                raise CheckbDirectiveError

            log.debug('Repo %s found in the whitelist', task_repo_url)
        except CheckbDirectiveError:
            raise CheckbDirectiveError("This repo is not allowed to post results into %s "
                                          "namespace. Not posting results." % checkname)

    def process(self, params, arg_data):
        # checking if reporting is enabled is done after importing yaml which
        # serves as validation of input results

        if 'file' in params and 'results' in params:
            raise CheckbDirectiveError("Either `file` or `results` can be used, not both.")

        try:
            if params.get('file', None):
                with open(params['file']) as resultfile:
                    params['results'] = resultfile.read()

            check_details = check.import_YAML(params['results'])
            log.debug("YAML output parsed OK.")
        except (CheckbValueError, IOError) as e:
            raise CheckbDirectiveError("Failed to load results: %s" % e)

        for detail in check_details:
            if not (detail.item and detail.report_type and detail.checkname):
                raise CheckbDirectiveError(
                    "The resultsdb directive requires 'item', 'type' and "
                    "'checkname' to be present in the YAML data.")

        conf = config.get_config()
        if not conf.report_to_resultsdb:
            log.info("Reporting to ResultsDB is disabled. Once enabled, the "
                     "following would get reported:\n%s", params['results'])
            return check.export_YAML(check_details)

        artifactsdir_url = '%s/%s' % (self.artifacts_baseurl, arg_data['uuid'])

        # for now, we're creating the resultsdb group at reporting time
        group_data = self.create_resultsdb_group(uuid=arg_data['uuid'])

        log.info('Posting %s results to ResultsDB...' % len(check_details))
        for detail in check_details:
            checkname = detail.checkname

            # find out if the task is allowed to post results into the namespace
            if config.get_config().profile == config.ProfileName.PRODUCTION:
                self.check_namespace(checkname, arg_data)

            self.ensure_testcase_exists(checkname)
            result_log_url = artifactsdir_url
            if detail.artifact:
                artifact_path = self.get_artifact_path(
                    arg_data['artifactsdir'],
                    detail.artifact
                    )
                if artifact_path:
                    result_log_url = "%s/%s" % (artifactsdir_url, artifact_path)
            try:
                result = self.resultsdb.create_result(
                    outcome=detail.outcome,
                    testcase=checkname,
                    groups=[group_data],
                    note=detail.note or None,
                    ref_url=result_log_url,
                    item=detail.item,
                    type=detail.report_type,
                    **detail.keyvals)
                log.debug('Result saved in ResultsDB:\n%s', pprint.pformat(result))
                detail._internal['resultsdb_result_id'] = result['id']

            except resultsdb_api.ResultsDBapiException as e:
                log.error(e)
                log.error("Failed to store to ResultsDB: `%s` `%s` `%s`",
                           detail.item, checkname, detail.outcome)

        return check.export_YAML(check_details)
