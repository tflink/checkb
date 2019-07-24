# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''This module contains custom Checkb exceptions'''

from __future__ import absolute_import


class CheckbError(Exception):
    '''Common ancestor for Checkb related exceptions'''
    pass


class CheckbValueError(ValueError, CheckbError):
    '''Checkb-specific :class:`ValueError`'''
    pass


class CheckbConfigError(CheckbError):
    '''All errors related to Checkb config files'''
    pass


class CheckbPlaybookError(CheckbError):
    '''Error in Ansible playbook file of the executed check'''
    pass


class CheckbDirectiveError(CheckbError):
    '''All errors related to Checkb directives'''
    pass


class CheckbRemoteError(CheckbError):
    '''All network and remote-server related errors'''
    def __init__(self, e=None, errno=None):
        if e:
            super(CheckbError, self).__init__(str(e))
        self.errno = errno


class CheckbRemoteTimeoutError(CheckbRemoteError):
    '''A remote-server did not send any output in a given timeout'''
    pass


class CheckbRemoteProcessError(CheckbRemoteError):
    '''A process/command executed remotely returned a non-zero exit code, crashed or failed in a
    different way'''
    pass


class CheckbNotImplementedError(CheckbError, NotImplementedError):
    '''NotImplementedError for Checkb classes, methods and functions'''


class CheckbImportError(CheckbError):
    '''All issues with Extensions'''

    def __init__(self, e):
        msg = str(e.message)
        if 'checkb' in msg:
            msg += "\nHint: Make sure that all required sub-packages are installed."
        super(CheckbError, self).__init__(msg)


class CheckbImageError(CheckbError):
    '''All generic image related errors'''
    pass


class CheckbImageNotFoundError(CheckbImageError):
    '''Requested image not found error'''
    pass


class CheckbPermissionError(CheckbError):
    '''Insufficient permissions or privileges'''
    pass


class CheckbInterruptError(CheckbError):
    '''The execution was interrupted. This might occur in certain parts of code
    when e.g. SIGINT or SIGTERM signals are received.

    :ivar int signum: number of raised signal
    :ivar str signame: name of raised signal. Can be also ``None`` or
        ``UNKNOWN``.
    '''

    def __init__(self, signum, signame):
        self.signum = signum
        self.signame = signame

    def __str__(self):
        return 'Received system signal %d (%s)' % (self.signum, self.signame)


class CheckbMinionError(CheckbError):
    '''All errors related to persistent or disposable minion handling'''
    pass
