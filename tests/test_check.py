# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Unit tests for checkb/check.py'''

import pytest
import yaml
from copy import deepcopy

from checkb import check
from checkb import exceptions as exc

class TestCheckDetail(object):

    def setup_method(self, method):
        '''Run this before every test invocation'''
        # for most methods, we want a default empty CheckDetail instance
        self.cd = check.CheckDetail(None)

    def test_init_empty(self):
        '''Test instance creation with empty parameters'''
        # by default, outcome should be 'NEEDS_INSPECTION', not empty
        assert self.cd.outcome == 'NEEDS_INSPECTION'
        assert not self.cd.item
        assert not self.cd.note
        assert not self.cd.output
        assert not self.cd.keyvals
        assert not self.cd.checkname

    def test_init_params(self):
        '''Test instance creation with non-empty parameters'''
        cd = check.CheckDetail(item='foo-1.2-3.fc20', outcome='FAILED',
                               note='untested', output=['line1', 'line2'],
                               checkname='testcheck', artifact='logfile.log')
        assert cd.item == 'foo-1.2-3.fc20'
        assert cd.outcome == 'FAILED'
        assert cd.note == 'untested'
        assert cd.checkname == 'testcheck'
        assert cd.artifact == 'logfile.log'

    def test_init_raise(self):
        '''Test instance creation that raises an error - invalid parameters'''
        with pytest.raises(exc.CheckbValueError):
            check.CheckDetail(None, outcome='INVALID TYPE')

        with pytest.raises(exc.CheckbValueError):
            check.CheckDetail(None, output='foobar')

        with pytest.raises(exc.CheckbValueError):
            check.CheckDetail(None, keyvals='foobar')

    def test_outcome(self):
        '''Test 'outcome' attribute'''
        # default value test
        # (already tested in constructor test, but it logically belongs here,
        # so let's include it again, in case constructor test changes)
        assert self.cd.outcome == 'NEEDS_INSPECTION'

        # test setter method with correct values
        self.cd.outcome = 'INFO'
        assert self.cd.outcome == 'INFO'

        self.cd.outcome = 'PASSED'
        assert self.cd.outcome == 'PASSED'

    def test_outcome_raise(self):
        '''Test 'outcome' attribute when it should raise an error'''
        with pytest.raises(exc.CheckbValueError):
            self.cd.outcome = 'INVALID OUTCOME TYPE'

    def test_update_outcome(self):
        '''Test 'update_outcome' method'''
        # basic use case
        self.cd.update_outcome('FAILED')
        assert self.cd.outcome == 'FAILED'

        # update_outcome respects the outcome priority ordering, it never
        # overrides a more important outcome with a less important one;
        # therefore it should retain FAILED here
        self.cd.update_outcome('PASSED')
        assert self.cd.outcome == 'FAILED'

        # None should do nothing
        self.cd.update_outcome(None)
        assert self.cd.outcome == 'FAILED'

    def test_update_outcome_raise(self):
        '''Test 'update_outcome' method when it should raise an error'''
        with pytest.raises(exc.CheckbValueError):
            self.cd.update_outcome('INVALID OUTCOME TYPE')

    def test_broken(self):
        '''Test 'broken' method'''
        # by default we're not broken
        assert not self.cd.broken()

        # two values should make it look broken
        self.cd.outcome = 'ABORTED'
        assert self.cd.broken()

        self.cd.outcome = 'CRASHED'
        assert self.cd.broken()

        # and we can go back to a non-broken state
        self.cd.outcome = 'FAILED'
        assert not self.cd.broken()

    def test_store(self, capsys):
        '''Test 'store' method'''
        # default use case where we fill 'output' and print to stdout as well
        self.cd.store('foobar')
        assert self.cd.output == ['foobar']
        out, err = capsys.readouterr()
        assert out == 'foobar\n'
        assert not err

        # use case without printing to stdout
        self.cd.store('barbaz', printout=False)
        assert self.cd.output == ['foobar', 'barbaz']
        out, err = capsys.readouterr()
        assert not out
        assert not err

    def test_cmp_outcome(self):
        '''Test 'cmp_outcome' method'''
        # sample comparisons where the first parameter is 'larger' (more
        # important) than the second one
        assert check.CheckDetail.cmp_outcome('FAILED', 'PASSED') == 1
        assert check.CheckDetail.cmp_outcome('NEEDS_INSPECTION', 'INFO') == 1
        assert check.CheckDetail.cmp_outcome('CRASHED', 'ABORTED') == 1
        assert check.CheckDetail.cmp_outcome('PASSED', None) == 1

        # sample comparisons where both the parameters are equal (same
        #importance)
        assert check.CheckDetail.cmp_outcome('PASSED', 'PASSED') == 0
        assert check.CheckDetail.cmp_outcome(None, None) == 0

        # sample comparisons where the first parameter is 'smaller' (less
        # important) than the second one
        assert check.CheckDetail.cmp_outcome('PASSED', 'FAILED') == -1
        assert check.CheckDetail.cmp_outcome(None, 'PASSED') == -1

    def test_cmp_outcome_raise(self):
        '''Test 'cmp_outcome' method when it should raise an error'''
        # test invalid outcome types as an input
        with pytest.raises(exc.CheckbValueError):
            assert check.CheckDetail.cmp_outcome('PASSED', 'INVALID OUTCOME')

        with pytest.raises(exc.CheckbValueError):
            assert check.CheckDetail.cmp_outcome('INVALID OUTCOME', 'FAILED')

        with pytest.raises(exc.CheckbValueError):
            assert check.CheckDetail.cmp_outcome('FOOBAR', 'FOOBAR')

    def test_create_multi_item_summary(self):
        '''Test create_multi_item_summary method'''
        # a basic use case with a list of strings
        summary = check.CheckDetail.create_multi_item_summary(['PASSED',
                  'PASSED', 'FAILED', 'ABORTED', 'INFO', 'INFO'])
        assert summary == '2 PASSED, 2 INFO, 1 FAILED, 1 ABORTED'

        # an empty list should return an empty string
        summary = check.CheckDetail.create_multi_item_summary([])
        assert summary == ''

        # a use case with one CheckDetail instance input
        summary = check.CheckDetail.create_multi_item_summary(self.cd)
        assert summary == '1 NEEDS_INSPECTION'

        # a use case with multiple CheckDetail instances input
        cd1 = check.CheckDetail(None, outcome='PASSED')
        cd2 = check.CheckDetail(None, outcome='PASSED')
        cd3 = check.CheckDetail(None, outcome='INFO')
        summary = check.CheckDetail.create_multi_item_summary([self.cd,
                  cd1, cd2, cd3])
        assert summary == '2 PASSED, 1 INFO, 1 NEEDS_INSPECTION'

    def test_create_multi_item_summary_raise(self):
        '''Test create_multi_item_summary method when it should raise an
           error'''
        # a single string input is not allowed, only a list of them
        with pytest.raises(exc.CheckbValueError):
            assert check.CheckDetail.create_multi_item_summary('PASSED')


class TestExportYAML(object):
    '''Test @method export_YAML'''
    item = 'xchat-0.5-1.fc20'
    outcome = 'PASSED'
    note = '5 ERRORS, 10 WARNINGS'
    report_type = check.ReportType.KOJI_BUILD
    keyvals = {"foo": "bar", "moo": 11}
    checkname = 'testcheck'
    artifact = 'logfile.log'
    _internal = {'resultsdb_result_id': 1234}

    def setup_method(self, method):
        self.cd = check.CheckDetail(item=self.item, outcome=self.outcome,
                                    note=self.note,
                                    report_type=self.report_type,
                                    keyvals=self.keyvals,
                                    checkname=self.checkname,
                                    artifact=self.artifact)
        self.cd._internal = self._internal


    def test_single_yaml(self):
        '''Test export with a single item section.'''
        yaml_output = check.export_YAML(self.cd)
        yaml_obj = yaml.safe_load(yaml_output)

        assert type(yaml_obj) is dict
        assert type(yaml_obj['results']) is list

        yaml_obj = yaml_obj['results'][0]

        assert yaml_obj['item'] == self.item
        assert yaml_obj['outcome'] == self.outcome
        assert yaml_obj['note'] == self.note
        assert yaml_obj['type'] == self.report_type
        assert yaml_obj['foo'] == self.keyvals['foo']
        assert yaml_obj['moo'] == self.keyvals['moo']
        assert yaml_obj['checkname'] == self.checkname
        assert yaml_obj['_internal'] == self._internal

    def test_invalid_keyvals(self):
        '''Test export with keyvals containing reserved keys.'''
        cd = deepcopy(self.cd)

        for key in check.RESERVED_KEYS:
            cd.keyvals[key] = 'foo'

        yaml_output = check.export_YAML(cd)
        yaml_obj = yaml.load(yaml_output, Loader=yaml.SafeLoader)['results'][0]

        assert yaml_obj['item'] == self.item
        assert yaml_obj['outcome'] == self.outcome
        assert yaml_obj['note'] == self.note
        assert yaml_obj['type'] == self.report_type
        assert yaml_obj['foo'] == self.keyvals['foo']
        assert yaml_obj['moo'] == self.keyvals['moo']
        assert yaml_obj['checkname'] == self.checkname
        assert yaml_obj['_internal'] == self._internal

    def test_multi(self):
        '''Test export with multiple item sections'''
        cd2 = check.CheckDetail(item='foobar-1.2-3.fc20', outcome='FAILED',
                                note='dependency error',
                                report_type=check.ReportType.BODHI_UPDATE)
        cd3 = check.CheckDetail(item='f20-updates', outcome='INFO',
                                note='2 stale updates',
                                report_type=check.ReportType.KOJI_TAG)
        yaml_output = check.export_YAML([self.cd, cd2, cd3])
        yaml_obj = yaml.safe_load(yaml_output)

        assert len(yaml_obj['results']) == 3
        assert yaml_obj['results'][0]['item'] == self.cd.item
        assert yaml_obj['results'][1]['item'] == cd2.item
        assert yaml_obj['results'][2]['item'] == cd3.item

    def test_invalid_missing_item(self):
        '''Test invalid input parameters'''
        with pytest.raises(exc.CheckbValueError):
            self.cd.item = None
            check.export_YAML(self.cd)

    def test_minimal(self):
        '''Test that empty CheckDetail values don't produce empty YAML lines,
        for example 'note:' should not be present if there's no
        CheckDetail.note'''
        cd = check.CheckDetail('foo')
        yaml_output = check.export_YAML(cd)
        yaml_obj = yaml.safe_load(yaml_output)['results'][0]

        # the output should look like this:
        #
        # results:
        #   - item: XXX
        #     outcome: XXX
        #
        # ('outcome:' is technically not a mandatory line, but with CheckDetail
        # export we produce it every time)
        assert len(yaml_obj) == 2


    def test_custom_report_type(self):
        '''Test that user can specify a custom CheckDetail.report_type'''
        self.cd.report_type = 'My Custom Type'
        yaml_output = check.export_YAML(self.cd)
        yaml_obj = yaml.safe_load(yaml_output)['results'][0]

        assert yaml_obj['type'] == self.cd.report_type


class TestImportYAML(object):
    '''Test @method import_YAML'''
    item = 'xchat-0.5-1.fc20'
    outcome = 'PASSED'
    note = '5 ERRORS, 10 WARNINGS'
    report_type = check.ReportType.KOJI_BUILD
    keyvals = {"foo": "bar", "moo": 11}
    checkname = 'testcheck'
    artifact = 'logfile.log'
    _internal = {'resultsdb_result_id': 1234}

    yaml_output = """
results:
  - item: xchat-0.5-1.fc20
    outcome: PASSED
    artifact: logfile.log
    note: 5 ERRORS, 10 WARNINGS
    type: koji_build
    foo: bar
    moo: 11
    checkname: testcheck
    _internal:
        resultsdb_result_id: 1234
"""

    def setup_method(self, method):
        self.cd = check.CheckDetail(item=self.item, outcome=self.outcome,
                                    note=self.note,
                                    report_type=self.report_type,
                                    keyvals=self.keyvals,
                                    checkname=self.checkname,
                                    artifact=self.artifact)
        self.cd._internal = self._internal

    def test_import(self):
        cds = check.import_YAML(self.yaml_output)

        assert len(cds) == 1
        assert isinstance(cds[0], check.CheckDetail)

        cd = cds[0]
        assert cd.item == self.cd.item
        assert cd.outcome == self.cd.outcome
        assert cd.note == self.cd.note
        assert cd.report_type == self.cd.report_type
        assert cd.keyvals == self.keyvals
        assert cd.checkname == self.checkname
        assert cd.artifact == self.artifact
        assert cd._internal == self._internal

    def test_import_exported(self):
        yaml_output = check.export_YAML(self.cd)

        cds = check.import_YAML(yaml_output)

        assert len(cds) == 1
        assert isinstance(cds[0], check.CheckDetail)

        cd = cds[0]
        assert cd.item == self.cd.item
        assert cd.outcome == self.cd.outcome
        assert cd.note == self.cd.note
        assert cd.report_type == self.cd.report_type
        assert cd.keyvals == self.keyvals
        assert cd.checkname == self.checkname
        assert cd.artifact == self.artifact
        assert cd._internal == self._internal

    def test_no_yaml(self):
        yaml_output = None
        with pytest.raises(exc.CheckbValueError):
            check.import_YAML(yaml_output)

    def test_invalid_yaml(self):
        yaml_output = "key:value\nkey: value"
        with pytest.raises(exc.CheckbValueError):
            check.import_YAML(yaml_output)

    def test_invalid_yaml_root_element_type(self):
        yaml_output = "[]"
        with pytest.raises(exc.CheckbValueError):
            check.import_YAML(yaml_output)

    def test_invalid_yaml_missing_results_key(self):
        yaml_output = "{}"
        with pytest.raises(exc.CheckbValueError):
            check.import_YAML(yaml_output)

    def test_invalid_yaml_wrong_results_type(self):
        yaml_output = "{'results': {}}"
        with pytest.raises(exc.CheckbValueError):
            check.import_YAML(yaml_output)

    def test_no_results(self):
        yaml_output = "{'results': []}"
        cds = check.import_YAML(yaml_output)
        assert len(cds) == 0

        yaml_output = "{'results': null}"
        cds = check.import_YAML(yaml_output)
        assert len(cds) == 0
