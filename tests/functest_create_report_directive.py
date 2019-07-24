# -*- coding: utf-8 -*-
# Copyright 2009-2016, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import pytest
import os

from checkb.directives import create_report_directive
from checkb import check


@pytest.mark.usefixtures('setup')
class TestCreateReportDirective():

    @pytest.fixture
    def setup(self, tmpdir):
        self.artifactsdir = tmpdir.mkdir('artifacts')
        self.report_filename = 'report.html'

        self.cd = check.CheckDetail(
            item='foo_bar',
            report_type=check.ReportType.KOJI_BUILD,
            outcome='NEEDS_INSPECTION',
            note='foo_bar note',
            output=["foo\nbar"],
            keyvals={"foo": "moo1", "bar": "moo2"},
            artifact='artifact.log',
        )

        self.yaml = check.export_YAML(self.cd)

        self.ref_params = {
            'results': self.yaml,
            'artifactsdir': self.artifactsdir.strpath,
        }
        self.ref_arg_data = {
            'resultsdb_job_id': 1,
            'checkname': 'test_resultsdb_report',
            'jobid': 'all/123',
            'uuid': 'c25237a4-b6b3-11e4-b98a-3c970e018701',
        }

        self.rd = create_report_directive.CreateReportDirective()

    def test_param_results(self, tmpdir):

        self.rd.process(self.ref_params, self.ref_arg_data)

        report_file = os.path.join(self.artifactsdir.strpath, self.report_filename)
        assert os.path.isfile(report_file)
        assert os.path.getsize(report_file) > 0

    def test_param_file(self, tmpdir):

        del self.ref_params['results']
        input_file = tmpdir.join('results.yaml')
        input_file.write(self.yaml)
        self.ref_params['file'] = input_file.strpath

        self.rd.process(self.ref_params, self.ref_arg_data)

        report_file = os.path.join(self.artifactsdir.strpath, self.report_filename)
        assert os.path.isfile(report_file)
        assert os.path.getsize(report_file) > 0

    def test_param_path(self, tmpdir):

        self.ref_params['path'] = 'my_dir/my_report.html'

        self.rd.process(self.ref_params, self.ref_arg_data)

        report_file = os.path.join(self.artifactsdir.strpath, self.ref_params['path'])
        assert os.path.isfile(report_file)
        assert os.path.getsize(report_file) > 0
