# -*- coding: utf-8 -*-
# Copyright 2009-2016, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import pytest
import mock

from checkb.directives import create_report_directive
from checkb.exceptions import CheckbDirectiveError

from checkb import check


@pytest.mark.usefixtures('setup')
class TestCreateReportDirective():

    @pytest.fixture
    def setup(self):
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

        self.ref_params = {'results': self.yaml}
        self.ref_arg_data = {
            'resultsdb_job_id': 1,
            'checkname': 'test_resultsdb_report',
            'jobid': 'all/123',
            'uuid': 'c25237a4-b6b3-11e4-b98a-3c970e018701',
            'artifactsdir': '/some/directory/',
        }

        self.rd = create_report_directive.CreateReportDirective()

    def test_failed_yaml_import(self, monkeypatch):
        import_YAML = mock.Mock(side_effect=(CheckbDirectiveError('Testing Error')))
        monkeypatch.setattr(check, 'import_YAML', import_YAML)

        with pytest.raises(CheckbDirectiveError):
            self.rd.process(self.ref_params, self.ref_arg_data)

    def test_params_results_file(self, monkeypatch):
        '''Params `results` and `file` can't be used together'''

        self.ref_params['file'] = '/some/file'

        with pytest.raises(CheckbDirectiveError):
            self.rd.process(self.ref_params, self.ref_arg_data)
