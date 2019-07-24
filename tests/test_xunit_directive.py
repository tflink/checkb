# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

from checkb.directives import xunit_directive
from checkb.exceptions import CheckbDirectiveError
from checkb.check import import_YAML

import mock
import pytest
import xunitparser

OUTPUT = 'I shall not use Czech in source code'

XML = """<?xml version="1.0"?>
<testsuite errors="0" failures="0" name="pytest" skips="0" tests="3" time="17.131">
<testcase classname="test.TestClass" file="test.py" line="30" name="test1" time="2.76759004593">
<system-out></system-out></testcase>
<testcase classname="test.TestClass" file="test.py" line="34" name="test2" time="2.67303919792">
<system-out></system-out></testcase>
<testcase classname="test.TestClass" file="test.py" line="52" name="test3" time="11.6780951023">
<system-out></system-out></testcase></testsuite>"""


class TestCheckParams(object):

    def setup(self):
        self.params = {'item': 'some_item',
                       'type': 'some_type',
                       'checkname': 'some_check',
                       'file': 'json.xml'}
        self.directive = xunit_directive.XunitDirective()

    @pytest.fixture
    def mock_parse(self, monkeypatch):
        stub_parse = mock.MagicMock(return_value=([], True))
        monkeypatch.setattr(xunitparser, 'parse', stub_parse)

    @pytest.fixture
    def mock_open(self, monkeypatch, read_data=None):
        self._mock_open(monkeypatch, read_data)

    def _mock_open(self, monkeypatch, read_data=None):
        monkeypatch.setattr(xunit_directive, 'open', mock.mock_open(read_data=read_data),
                            raising=False)

    def test_basic(self, monkeypatch, mock_parse, mock_open):
        monkeypatch.setattr(xunit_directive, 'export_YAML', mock.Mock(return_value=OUTPUT))

        output = self.directive.process(self.params, None)
        assert output == OUTPUT

    def test_file_not_present(self, mock_parse, mock_open):
        self.params.pop('file')
        self.params = {'fila': 'json.xml'}

        with pytest.raises(CheckbDirectiveError):
            self.directive.process(self.params, None)

    def test_item_not_present(self, mock_parse, mock_open):
        self.params.pop('item')

        with pytest.raises(CheckbDirectiveError):
            self.directive.process(self.params, None)

    def test_type_not_present(self, mock_parse, mock_open):
        self.params.pop('type')

        with pytest.raises(CheckbDirectiveError):
            self.directive.process(self.params, None)

    def test_checkname_not_present(self, mock_parse, mock_open):
        self.params.pop('checkname')

        with pytest.raises(CheckbDirectiveError):
            self.directive.process(self.params, None)

    def test_file_does_not_exist(self, mock_parse):
        with pytest.raises(IOError):
            self.directive.process(self.params, None)

    def test_aggregation_unknown(self, mock_parse):
        self.params['aggregation'] = 'allfail'

        with pytest.raises(CheckbDirectiveError):
            self.directive.process(self.params, None)

    def test_aggregation_none(self, monkeypatch):
        self.params['aggregation'] = 'none'
        self._mock_open(monkeypatch, read_data=XML)

        output = self.directive.process(self.params, None)
        assert len(import_YAML(output)) == 3

    def test_aggregation_allpass(self, monkeypatch):
        self.params['aggregation'] = 'allpass'
        self._mock_open(monkeypatch, read_data=XML)

        output = self.directive.process(self.params, None)
        assert len(import_YAML(output)) == 1

    def test_aggregation_allpass_default(self, monkeypatch):
        self._mock_open(monkeypatch, read_data=XML)

        output = self.directive.process(self.params, None)
        assert len(import_YAML(output)) == 1
