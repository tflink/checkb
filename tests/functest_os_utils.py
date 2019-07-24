# -*- coding: utf-8 -*-
# Copyright 2016, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Functional tests for checkb.os_utils'''

import subprocess
import pytest

from checkb.os_utils import popen_rt


class TestPopenRT(object):
    '''Test os_utils.popen_rt()'''

    def test_exitcode_zero(self):
        out, err = popen_rt(['true'])
        assert not out
        assert not err

    def test_exitcode_nonzero(self):
        cmd = ['false']
        with pytest.raises(subprocess.CalledProcessError) as excinfo:
            popen_rt(cmd)
        err = excinfo.value
        assert err.returncode > 0
        assert err.cmd == cmd
        assert not err.output

    def test_stdout(self):
        text = 'Lorem ipsum'
        out, err = popen_rt(['echo', '-n', text])
        assert out == text
        assert not err

    def test_stderr(self):
        text = 'Lorem ipsum'
        out, err = popen_rt('echo -n %s >&2' % text, shell=True, stderr=subprocess.PIPE)
        assert not out
        assert err == text

    def test_stream_merge(self):
        text_out = 'this is stdout'
        text_err = 'this is stderr'
        out, err = popen_rt('echo -n %s; echo -n %s >&2' % (text_out, text_err), shell=True)
        assert out == text_out + text_err
        assert not err

    def test_stream_separate(self):
        text_out = 'this is stdout'
        text_err = 'this is stderr'
        out, err = popen_rt('echo -n %s; echo -n %s >&2' % (text_out, text_err), shell=True,
                            stderr=subprocess.PIPE)
        assert out == text_out
        assert err == text_err

    def test_shell(self):
        popen_rt('true && true', shell=True)

    def test_stdin(self, tmpdir):
        text = 'foo\nbar'
        infile = tmpdir.join('stdin')
        infile.write(text)
        out, err = popen_rt(['cat'], stdin=infile.open())
        assert out == text
        assert not err
