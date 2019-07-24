# -*- coding: utf-8 -*-
# Copyright 2009-2016, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import pytest
import mock
import configparser

from checkb.directives import resultsdb_directive

from checkb import check
from checkb import config
import checkb.exceptions as exc


class StubConfigParser(object):
    def read(self, *args):
        pass

    def __getitem__(self, key):
        return {'url': 'giturl/testname'}


@pytest.mark.usefixtures('setup')
class TestResultsdbDirective():
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

        self.yaml = check.export_YAML(self.cd)

        self.ref_input = {'results': self.yaml}
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
        self.ref_jobdata = {u'end_time': None,
                            u'href': u'http://127.0.0.1/api/v2.0/jobs/%d' % self.ref_jobid,
                            u'id': self.ref_jobid,
                            u'name': self.cd.checkname,
                            u'ref_url': self.ref_refurl,
                            u'results': [],
                            u'results_count': 0,
                            u'start_time': None,
                            u'status': u'SCHEDULED'}

        self.stub_rdb = mock.Mock(**{
            'get_testcase.return_value': {},
            'create_job.return_value': self.ref_jobdata,
            'create_result.return_value': self.ref_resultdata,
            })
        self.test_rdb = resultsdb_directive.ResultsdbDirective(self.stub_rdb)

        # while it appears useless, this actually sets config in several tests
        monkeypatch.setattr(config, '_config', None)
        self.conf = config.get_config()
        self.conf.report_to_resultsdb = True

        monkeypatch.setattr(configparser, 'ConfigParser', StubConfigParser)

    def test_param_file(self, tmpdir):
        del self.ref_input['results']
        input_file = tmpdir.join('results.yaml')
        input_file.write(self.yaml)
        self.ref_input['file'] = input_file.strpath

        self.test_rdb.process(self.ref_input, self.ref_arg_data)

        # Given the input data, the resultsdb should be called once, and only
        #   once, calling "create_result".
        # This assert failing either means that more calls were added in the
        #   source code, or that a bug is present, and "create_result" is
        #   called multiple times.
        # we expect rdb to be called 2 times:
        # check for testcase, and report result

        assert len(self.stub_rdb.method_calls) == 2

        # Select the keyword arguments of create_results call
        call_data = self.stub_rdb.create_result.call_args[1]

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

    def test_file_missing(self, tmpdir):
        del self.ref_input['results']
        input_file = tmpdir.join('results.yaml')
        self.ref_input['file'] = input_file.strpath

        with pytest.raises(exc.CheckbDirectiveError):
            self.test_rdb.process(self.ref_input, self.ref_arg_data)

        assert len(self.stub_rdb.method_calls) == 0
