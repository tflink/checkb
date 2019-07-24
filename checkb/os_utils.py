# -*- coding: utf-8 -*-
# Copyright 2009-2016, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

''' Utility methods related to an operating system '''

from __future__ import absolute_import
from __future__ import print_function
import os
import subprocess

from checkb.logger import log
import checkb.exceptions as exc


def is_root():
    '''Determine whether we're currently running under the root account.

    :rtype: bool
    '''
    return os.geteuid() == 0


def has_sudo():
    '''Determine whether we currently have a password-less access to sudo.

    Note: It's not possible to say whether the access will stay password-less in the future (the
    credentials might be set to expire in time), just for this exact moment.

    :rtype: bool
    '''
    # Note: We could run "sudo --reset-timestamp" first to make sure any cached password is
    # invalidated and therefore be sure we always have a password-less access. But this might be
    # seen as an impolite thing to do (esp. when we're not granted the sudo access, we would still
    # reset the cache with every run) and it might obstruct some use cases. Not implemented ATM.
    cmd = ['sudo', '--validate', '--non-interactive']
    log.debug('Deciding whether we have a password-less sudo access. Running: %s', ' '.join(cmd))

    try:
        subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        log.debug(u"✘ Sudo access is not available. Received exit code %d and output:\n%s",
                  e.returncode, e.output.rstrip())
        return False
    else:
        log.debug(u'✔ Sudo access is available')
        return True


def popen_rt(cmd, stderr=subprocess.STDOUT, bufsize=1, **kwargs):
    """This is similar to :func:`subprocess.check_output`, but with real-time printing to console
    as well. It is useful for longer-running tasks for which you'd like to both capture the output
    and also see it printed in terminal continuously.

    Please note that by default both ``stdout`` and ``stderr`` are merged together. You can use
    ``stderr=subprocess.PIPE``, and it will be returned to you separated, but it won't be printed
    out to console (only ``stdout`` will).

    The parameters are the same as for :class:`subprocess.Popen`. You can't use ``stdout``
    parameter, that one is hardcoded to :attr:`subprocess.PIPE`.

    :return: tuple of ``(stdoutdata, stderrdata)``. ``stderrdata`` will be ``None`` by default
        (because ``stderr`` is redirected to ``stdout``).
    :raise CheckbValueError: if you provide ``stdout`` parameter
    :raise subprocess.CalledProcessError: if the command exits with non-zero exit code (helpful
        attributes are provided, study its documentation)
    """
    if 'stdout' in kwargs:
        raise exc.CheckbValueError('stdout parameter not allowed, it will be overridden')

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=stderr, bufsize=bufsize,
        universal_newlines=True, **kwargs)
    output = []
    for line in iter(proc.stdout.readline, ''):
        print(line, end='')
        output.append(line)

    (stdoutdata, stderrdata) = proc.communicate()
    assert proc.returncode is not None
    assert not stdoutdata
    if stderr == subprocess.STDOUT:
        assert not stderrdata

    stdoutdata = ''.join(output)

    if proc.returncode:
        raise subprocess.CalledProcessError(proc.returncode, cmd, stdoutdata)

    return (stdoutdata, stderrdata)
