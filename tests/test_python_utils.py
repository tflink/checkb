# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Unit tests for checkb/python_utils.py'''

import pytest

from checkb import python_utils
import checkb.exceptions as exc
from checkb.python_utils import basestring


class TestCollectionOf:
    '''This tests `iterable` and `sequence`.'''

    def test_iterable(self):
        assert python_utils.iterable([1, 2])
        assert python_utils.iterable(['a', 'b'])
        assert python_utils.iterable(('foo',))
        assert python_utils.iterable({'foo', 'bar', 'baz'})
        assert python_utils.iterable(set())
        assert python_utils.iterable(())
        assert python_utils.iterable([u'foo', u'bar'])
        assert python_utils.iterable({'a': 1, 'b': 2})

    def test_not_iterable(self):
        assert not python_utils.iterable('a')
        assert not python_utils.iterable(u'a')
        try:
            assert not python_utils.iterable(unicode('foo'))
        except NameError:
            # Python 3 no such thing as unicode, str already tested
            pass
        assert not python_utils.iterable(3)
        assert not python_utils.iterable(3.14)
        assert not python_utils.iterable(None)
        assert not python_utils.iterable(object())

    def test_iterable_items(self):
        assert python_utils.iterable([1, 2], int)
        assert not python_utils.iterable([1, 2], float)
        assert not python_utils.iterable([1, 2.2], float)

        assert python_utils.iterable(['a', 'b'], str)
        assert python_utils.iterable(['a', 'b'], basestring)
        try:
            assert not python_utils.iterable(['a', 'b'], unicode)
        except NameError:
            # Python 3 no such thing as unicode, str already tested
            pass
        assert python_utils.iterable([[], []], list)

        # empty classes
        X = type('X', (object,), {})
        Y = type('Y', (X,), {})
        assert python_utils.iterable((X(), X()), X)
        assert python_utils.iterable((X(), Y()), X)
        assert not python_utils.iterable((X(), Y()), Y)

    def test_raise(self):
        with pytest.raises(exc.CheckbValueError):
            assert python_utils.iterable([1, 2], 1)

        with pytest.raises(exc.CheckbValueError):
            assert python_utils.iterable([1, 2], 'a')

        with pytest.raises(exc.CheckbValueError):
            assert python_utils.iterable([1, 2], [])

        X = type('X', (object,), {})
        with pytest.raises(exc.CheckbValueError):
            assert python_utils.iterable([1, 2], X())

    def test_sequence(self):
        assert python_utils.sequence([1, 2])
        assert python_utils.sequence(['a', 'b'])
        assert python_utils.sequence(('foo',))
        assert python_utils.sequence(())
        assert python_utils.sequence([u'foo', u'bar'])

    def test_not_sequence(self):
        assert not python_utils.sequence({'foo', 'bar', 'baz'})
        assert not python_utils.sequence(set())
        assert not python_utils.sequence({'a': 1, 'b': 2})


class TestReverseArgparse(object):

    def test_no_input(self):
        ref_input = {}
        output = python_utils.reverse_argparse(ref_input)
        assert output == []

    def test_long_option(self):
        ref_input = {'item': 'foo'}
        output = python_utils.reverse_argparse(ref_input)
        assert output == ['--item', 'foo']

    def test_short_option(self):
        ref_input = {'i': 'foo'}
        output = python_utils.reverse_argparse(ref_input)
        assert output == ['-i', 'foo']

    def test_boolean(self):
        ref_input = {'debug': True}
        output = python_utils.reverse_argparse(ref_input)
        assert output == ['--debug']

    def test_boolean_false(self):
        ref_input = {'debug': False}
        output = python_utils.reverse_argparse(ref_input)
        assert output == []

    def test_none(self):
        ref_input = {'item': None}
        output = python_utils.reverse_argparse(ref_input)
        assert output == []

    def test_list(self):
        ref_input = {'arch': ['x86_64', 'i386']}
        output = python_utils.reverse_argparse(ref_input)
        assert len(output) == 4
        assert output[0] == '--arch'
        assert output[2] == '--arch'
        assert 'x86_64' in output
        assert 'i386' in output

    def test_number(self):
        ref_input = {'count': 1234}
        output = python_utils.reverse_argparse(ref_input)
        assert output == ['--count', '1234']

    def test_underscore_to_dash(self):
        ref_input = {'job_id': 1234}
        output = python_utils.reverse_argparse(ref_input)
        assert output == ['--job-id', '1234']

    def test_ignore(self):
        ref_input = {'item': 'foo'}
        output = python_utils.reverse_argparse(ref_input, ignore=('item'))
        assert output == []

    def test_ignore_more_options(self):
        ref_input = {'item': 'foo', 'type': 'koji_tag'}
        output = python_utils.reverse_argparse(ref_input, ignore=('item'))
        assert output == ['--type', 'koji_tag']

    def test_multiple_ignore(self):
        ref_input = {'item': 'foo', 'type': 'koji_tag'}
        output = python_utils.reverse_argparse(ref_input, ignore=('item', 'type'))
        assert output == []

    def test_ignore_underscore(self):
        ref_input = {'job_id': 1234}
        output = python_utils.reverse_argparse(ref_input, ignore=('job_id'))
        assert output == []
        output = python_utils.reverse_argparse(ref_input, ignore=('job-id'))
        assert output == ['--job-id', '1234']

    def test_complex(self):
        ref_input = {'item': 'foo', 'debug': True, 'arch': ['x86_64', 'i386'], 'job_id': 1234,
                     't': 'koji', 'override': ['foo=bar'], 'ignore_me': True}
        ref_ignore = ['ignore_me', 'extra_ignore']
        ref_output = ['--item', 'foo', '--debug', '--arch', 'x86_64', '--arch', 'i386',
                      '--job-id', '1234', '-t', 'koji', '--override', 'foo=bar']
        output = python_utils.reverse_argparse(ref_input, ignore=ref_ignore)
        assert sorted(ref_output) == sorted(output)
        assert output.index('--item') == output.index('foo') - 1
        assert output.index('--job-id') == output.index('1234') - 1
        assert output.index('-t') == output.index('koji') - 1
        assert output.index('--override') == output.index('foo=bar') - 1
