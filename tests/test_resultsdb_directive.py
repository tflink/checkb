# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

"""Unit tests for checkb/directives/resultsdb_directive.py"""

import os
import pytest
import mock
import configparser

from checkb.directives import resultsdb_directive
from checkb.exceptions import CheckbDirectiveError, CheckbValueError

from checkb import check
from checkb import config
from checkb import config_defaults

from resultsdb_api import ResultsDBapiException


class StubConfigParser(object):
    def read(self, *args):
        pass

    def __getitem__(self, key):
        return {'url': 'giturl/testname'}


@pytest.mark.usefixtures('setup')
class TestResultsdbReport():

    @pytest.fixture
    def setup(self, monkeypatch):
        '''Run this before every test invocation'''

        self.cd = check.CheckDetail(
            item='foo_bar',
            report_type=check.ReportType.KOJI_BUILD,
            outcome='NEEDS_INSPECTION',
            note='foo_bar note',
            output=["foo\nbar"],
            keyvals={"foo": "moo1", "bar": "moo2"},
            checkname='qa.test_resultsdb_report',
            )

        self.update_input()

        self.ref_arg_data = {
                'resultsdb_job_id': 1,
                'jobid': 'all/123',
                'uuid': 'c25237a4-b6b3-11e4-b98a-3c970e018701',
                'artifactsdir': '/some/directory/',
                'task': '/taskdir',
                'item': 'firefox-45.0.2-1.fc23'
                }

        self.ref_resultdata = {u'id': 1234}

        self.ref_jobid = 1234
        self.ref_uuid = 'c25237a4-b6b3-11e4-b98a-3c970e018701'
        self.ref_refurl = u'http://example.com/%s' % self.cd.checkname
        self.ref_jobdata = {'ref_url': self.ref_refurl,
                            'uuid': 'c25237a4-b6b3-11e4-b98a-3c970e018701',
                            'description': self.cd.checkname}

        self.stub_rdb = mock.Mock(**
            {'get_testcase.return_value': {},
             'create_job.return_value': self.ref_jobdata,
             'create_result.return_value': self.ref_resultdata,
            })
        self.test_rdb = resultsdb_directive.ResultsdbDirective(self.stub_rdb)

        # while it appears useless, this actually sets config in several tests
        monkeypatch.setattr(config, '_config', None)
        self.conf = config.get_config()
        self.conf.report_to_resultsdb = True

        monkeypatch.setattr(configparser, 'ConfigParser', StubConfigParser)

    def update_input(self):
        self.yaml = check.export_YAML(self.cd)
        self.ref_input = {'results': self.yaml}

    def test_config_reporting_disabled(self):
        """Checks config option that disables reporting."""
        conf = config.get_config()

        conf.report_to_resultsdb = False

        yaml = self.test_rdb.process(self.ref_input, self.ref_arg_data)
        cds = check.import_YAML(yaml)
        my_cd = check.import_YAML(check.export_YAML(self.cd))
        # return value should be the same YAML
        assert len(cds) == 1
        assert cds[0].__dict__ == my_cd[0].__dict__

        # no call should have been made
        assert len(self.stub_rdb.mock_calls) == 0

        config._config = None

    def test_failed_yaml_import(self, monkeypatch):
        """Checks if failed YAML import raises exception"""
        mock_import_yaml = mock.Mock(
            side_effect=CheckbValueError("Testing Error"))
        monkeypatch.setattr(check, 'import_YAML', mock_import_yaml)

        with pytest.raises(CheckbDirectiveError):
            self.test_rdb.process(self.ref_input, self.ref_arg_data)

    def test_yaml_missing_item(self):
        """Checks if missing item raises exception"""
        yaml = ""
        for line in self.ref_input['results'].split('\n'):
            if 'item:' in line:
                continue
            yaml += line + '\n'

        with pytest.raises(CheckbDirectiveError):
            self.test_rdb.process({"results": yaml}, self.ref_arg_data)

    def test_yaml_missing_type(self):
        """Checks if missing type raises exception"""
        yaml = ""
        for line in self.ref_input['results'].split('\n'):
            if 'type:' in line:
                continue
            yaml += line + '\n'

        with pytest.raises(CheckbDirectiveError):
            self.test_rdb.process({"results": yaml}, self.ref_arg_data)

    def test_yaml_missing_checkname(self):
        """Checks if missing checkname raises exception"""
        yaml = ""
        for line in self.ref_input['results'].split('\n'):
            if 'checkname:' in line:
                continue
            yaml += line + '\n'

        with pytest.raises(CheckbDirectiveError):
            self.test_rdb.process({"results": yaml}, self.ref_arg_data)

    def test_report(self):
        """Checks whether YAML is correctly mapped to the reporting method's
        arguments."""

        self.test_rdb.process(self.ref_input, self.ref_arg_data)

        # Given the input data, the resultsdb should be called once, and only
        #   once, calling "create_result".
        # This assert failing either means that more calls were added in the
        #   source code, or that a bug is present, and "create_result" is
        #   called multiple times.
        # we expect rdb to be called 2 times:
        # check for testcase, and report result

        assert len(self.stub_rdb.mock_calls) == 2

        # Select the first call of "create_result" method.
        # This could be written as self.stub_rdb.calls()[0] at the moment, but
        #   this is more future-proof, and accidental addition of resultsdb
        #   calls is handled by the previous assert.
        call = [call for call in self.stub_rdb.mock_calls
            if call[0] == 'create_result'][0]
        # Select the keyword arguments of that call
        call_data = call[2]

        # the log url depends on the arg_data, so construct it here
        ref_log_url = '%s/%s' % (self.conf.artifacts_baseurl, self.ref_arg_data['uuid'])

        assert call_data['testcase'] == self.cd.checkname
        assert call_data['outcome'] == self.cd.outcome
        assert call_data['note'] == self.cd.note
        assert call_data['ref_url'] == ref_log_url
        assert call_data['item'] == self.cd.item
        assert call_data['type'] == self.cd.report_type
        assert len(call_data['groups']) == 1
        group = call_data['groups'][0]
        assert group['uuid'] == self.ref_uuid
        assert group['ref_url'] == "%s/%s" % (self.test_rdb.execdb_server, self.ref_uuid)

        assert 'output' not in call_data.keys()

        for key in self.cd.keyvals.keys():
            assert call_data[key] == self.cd.keyvals[key]

    def test_empty_results(self):
        """When there are no results, it shouldn't crash, just do nothing"""
        yaml1 = 'results:'
        yaml2 = 'results: []'

        for ref_yaml in [yaml1, yaml2]:
            self.test_rdb.process({'results': ref_yaml}, self.ref_arg_data)
            assert len(self.stub_rdb.mock_calls) == 0

    def test_empty_file(self):
        """Should raise for a completely empty file"""

        with pytest.raises(CheckbDirectiveError):
            self.test_rdb.process({'results': ''}, self.ref_arg_data)

        assert len(self.stub_rdb.mock_calls) == 0

    def test_both_file_and_results(self, monkeypatch):
        ref_input = {'results': 'foobar', 'file': 'foo.bar'}
        with pytest.raises(CheckbDirectiveError):
            self.test_rdb.process(ref_input, self.ref_arg_data)

    def test_get_artifact_path(self, monkeypatch):
        artifactsdir = '/path/to/artifacts'
        rel_artifact = 'some/relative/file.log'
        abs_artifact = os.path.join(artifactsdir, rel_artifact)

        monkeypatch.setattr(resultsdb_directive.os.path, 'exists', lambda x: True)
        assert self.test_rdb.get_artifact_path(artifactsdir, rel_artifact) == rel_artifact
        assert self.test_rdb.get_artifact_path(artifactsdir, abs_artifact) == rel_artifact

    def test_get_artifact_path_errors(self, monkeypatch):
        artifactsdir = '/path/to/artifacts'
        artifact = '/some/absolute/file.log'

        # if file does not exist None is expected
        monkeypatch.setattr(resultsdb_directive.os.path, 'exists', lambda x: False)
        assert self.test_rdb.get_artifact_path(artifactsdir, artifact) is None

        # if file exists, but is out of the artifactsdir, None is expected
        monkeypatch.setattr(resultsdb_directive.os.path, 'exists', lambda x: True)
        assert self.test_rdb.get_artifact_path(artifactsdir, artifact) is None

    def test_report_artifact_in_log_url(self, monkeypatch):
        """Checks whether artifact is correctly mapped to log_url"""
        cd = check.CheckDetail(
            item='foo_bar',
            report_type=check.ReportType.KOJI_BUILD,
            outcome='NEEDS_INSPECTION',
            note='foo_bar note',
            output=["foo\nbar"],
            keyvals={"foo": "moo1", "bar": "moo2"},
            checkname='qa.test_resultsdb_report',
            artifact='digest/logs/logfile.log'
            )
        monkeypatch.setattr(self.test_rdb, 'get_artifact_path', lambda *x: 'digest/logs/logfile.log')

        yaml = check.export_YAML(cd)
        ref_input = {'results': yaml}

        self.test_rdb.process(ref_input, self.ref_arg_data)

        # Given the input data, the resultsdb should be called once, and only
        #   once, calling "create_result".
        # This assert failing either means that more calls were added in the
        #   source code, or that a bug is present, and "create_result" is
        #   called multiple times.
        # we expect rdb to be called 4 times: create job, update to RUNNING,
        # check for testcase, report result and complete job

        assert len(self.stub_rdb.mock_calls) == 2

        # Select the first call of "create_result" method.
        # This could be written as self.stub_rdb.calls()[0] at the moment, but
        #   this is more future-proof, and accidental addition of resultsdb
        #   calls is handled by the previous assert.
        call = [call for call in self.stub_rdb.mock_calls
            if call[0] == 'create_result'][0]
        # Select the keyword arguments of that call
        call_data = call[2]

        # the log url depends on the arg_data, so construct it here
        ref_log_url = '%s/%s/%s' %\
                      (self.conf.artifacts_baseurl, self.ref_arg_data['uuid'], cd.artifact)

        assert call_data['ref_url'] == ref_log_url

    def test_create_group(self):
        # make sure that the proper API calls are made to create a resultsdb job
        test_jobdata = self.test_rdb.create_resultsdb_group(
            self.ref_uuid,
            self.cd.checkname,
            self.ref_refurl)

        assert test_jobdata == self.ref_jobdata

        rdb_calls = self.stub_rdb.mock_calls
        # we expect only one call to resultsdb when reporting a result
        assert len(rdb_calls) == 0

    def test_ensure_testcase_creation_notexist(self):
        # check to see if the testcase is created in the case that it doesn't
        # already exist

        self.stub_rdb.get_testcase.side_effect = ResultsDBapiException(
            'Testcase not found')

        self.test_rdb.ensure_testcase_exists(self.cd.checkname)

        rdb_calls = self.stub_rdb.mock_calls

        assert len(rdb_calls) == 2
        assert rdb_calls[0][0] == 'get_testcase'
        assert rdb_calls[1][0] == 'create_testcase'

    def test_ensure_testcase_creation_exists(self):
        # check to make sure that a testcase is _not_ created in the case that
        # it already exists

        self.test_rdb.ensure_testcase_exists(self.cd.checkname)

        rdb_calls = self.stub_rdb.mock_calls

        assert len(rdb_calls) == 1
        assert rdb_calls[0][0] == 'get_testcase'

    def test_ensure_testcase_cached(self):
        # check to make sure that ensure_testcase_exists does not query resultsdb unnecessarily

        self.test_rdb.ensure_testcase_exists(self.cd.checkname)
        self.test_rdb.ensure_testcase_exists(self.cd.checkname)

        rdb_calls = self.stub_rdb.mock_calls

        assert len(rdb_calls) == 1
        assert rdb_calls[0][0] == 'get_testcase'

    def test_yaml_output(self):
        """Checks whether YAML is correctly mapped to the reporting method's
        arguments."""

        output = self.test_rdb.process(self.ref_input, self.ref_arg_data)
        data = check.import_YAML(output)

        assert data[0]._internal['resultsdb_result_id'] == 1234

    def test_not_allowed_namespace(self, monkeypatch):
        ref_ns = {'namespaces_safe': [], 'namespaces_whitelist': {'qa': []}}
        monkeypatch.setattr(config, 'load_namespaces_config', lambda: ref_ns)
        self.conf.profile = config_defaults.ProfileName.PRODUCTION

        with pytest.raises(CheckbDirectiveError):
            self.test_rdb.process(self.ref_input, self.ref_arg_data)

    def test_allowed_namespace(self, monkeypatch):
        ref_ns = {'namespaces_safe': [], 'namespaces_whitelist': {'qa': ['giturl']}}
        monkeypatch.setattr(config, 'load_namespaces_config', lambda: ref_ns)
        self.conf.profile = config_defaults.ProfileName.PRODUCTION

        self.test_rdb.process(self.ref_input, self.ref_arg_data)
        # did not raise, pass

    def test_safe_namespace(self, monkeypatch):
        ref_ns = {'namespaces_safe': ['qa']}
        monkeypatch.setattr(config, 'load_namespaces_config', lambda: ref_ns)
        self.conf.profile = config_defaults.ProfileName.PRODUCTION

        self.test_rdb.process(self.ref_input, self.ref_arg_data)
        # did not raise, pass

    def test_not_allowed_namespace_prefix(self, monkeypatch):
        ref_ns = {'namespaces_safe': [], 'namespaces_whitelist': {'qa': ['giturl']}}
        monkeypatch.setattr(config, 'load_namespaces_config', lambda: ref_ns)
        self.cd.checkname = 'qa1.test_resultsdb_report'
        self.update_input()
        self.conf.profile = config_defaults.ProfileName.PRODUCTION

        with pytest.raises(CheckbDirectiveError):
            self.test_rdb.process(self.ref_input, self.ref_arg_data)

    def test_namespace_not_exist(self, monkeypatch):
        ref_ns = {'namespaces_safe': ['scratch'], 'namespaces_whitelist': {'qa': ['giturl']}}
        monkeypatch.setattr(config, 'load_namespaces_config', lambda: ref_ns)
        self.cd.checkname = 'qa1.test_resultsdb_report'
        self.update_input()
        self.conf.profile = config_defaults.ProfileName.PRODUCTION

        with pytest.raises(CheckbDirectiveError):
            self.test_rdb.process(self.ref_input, self.ref_arg_data)
