# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

from checkb import checkb_result
from checkb.check import CheckDetail, export_YAML, import_YAML
import mock
import os
import sys
import argparse

PYVER = sys.version_info.major
builtin_open = '__builtin__.open' if PYVER < 3 else 'builtins.open'

OUTPUT = ""

FILE = """results:
- item: punkipa
  outcome: PASSED
  type: beer
"""


def save_output(str):
    global OUTPUT
    OUTPUT = str


class TestCheckbResult(object):
    def test_empty_run(self, monkeypatch):
        test_args = mock.MagicMock()
        test_args.__dict__ = {'file': 'somefile', 'report_type': 'beer', 'item': 'punkipa',
                              'keyval': [], 'outcome': 'PASSED'}
        stub_parser = mock.MagicMock()
        stub_parser.parse_args = mock.MagicMock(return_value=test_args)
        stub_get_argparser = mock.MagicMock(return_value=stub_parser)
        monkeypatch.setattr(checkb_result, 'get_argparser', stub_get_argparser)

        stub_file = mock.MagicMock()
        stub_file.write = save_output

        with mock.patch(builtin_open, mock.MagicMock(return_value=stub_file), create=True):
            checkb_result.main()

        assert OUTPUT == export_YAML(CheckDetail(**vars(test_args)))

    def test_nonempty_run(self, monkeypatch):
        test_args = mock.MagicMock()
        test_args.__dict__ = {'file': 'somefile', 'report_type': 'beer', 'item': 'punkipa',
                              'keyval': [], 'outcome': 'PASSED'}
        stub_parser = mock.MagicMock()
        stub_parser.parse_args = mock.MagicMock(return_value=test_args)
        stub_get_argparser = mock.MagicMock(return_value=stub_parser)
        monkeypatch.setattr(checkb_result, 'get_argparser', stub_get_argparser)

        stub_file = mock.MagicMock()
        stub_file.write = save_output
        stub_file.read = lambda: FILE

        monkeypatch.setattr(os.path, 'isfile', mock.MagicMock(return_value=True))

        with mock.patch(builtin_open, mock.MagicMock(return_value=stub_file), create=True):
            checkb_result.main()

        assert OUTPUT == export_YAML(import_YAML(FILE)+[CheckDetail(**vars(test_args))])

    def test_keyval_parse(self, monkeypatch):
        test_args = mock.MagicMock()
        test_args.__dict__ = {'file': 'somefile', 'report_type': 'beer', 'item': 'punkipa',
                              'keyval': ['hop=Simcoe'], 'outcome': 'PASSED'}
        stub_parser = mock.MagicMock()
        stub_parser.parse_args = mock.MagicMock(return_value=test_args)
        stub_get_argparser = mock.MagicMock(return_value=stub_parser)
        monkeypatch.setattr(checkb_result, 'get_argparser', stub_get_argparser)

        stub_file = mock.MagicMock()
        stub_file.write = save_output

        with mock.patch(builtin_open, mock.MagicMock(return_value=stub_file), create=True):
            checkb_result.main()

        assert OUTPUT == export_YAML(CheckDetail(**vars(test_args)))

    def test_parser_creation(self):
        '''make sure parser creation doesn't crash'''
        parser = checkb_result.get_argparser()
        assert isinstance(parser, argparse.ArgumentParser)
