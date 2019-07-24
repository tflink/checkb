# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

''' Utility methods related to RPM '''

from __future__ import absolute_import
import functools
import re
import hawkey
import subprocess
import pipes

from checkb.logger import log
from checkb import exceptions as exc
from checkb import os_utils


def rpmformat(rpmstr, fmt='nvr', end_arch=False):
    '''
    Parse and convert an RPM package version string into a different format.
    String identifiers: N - name, E - epoch, V - version, R - release, A -
    architecture.

    :param str rpmstr: string to be manipulated in a format of N(E)VR
                       (``foo-1.2-3.fc20`` or ``bar-4:1.2-3.fc20``) or N(E)VRA
                       (``foo-1.2-3.fc20.x86_64`` or ``bar-4:1.2-3.fc20.i686``)
    :param str fmt: desired format of the string to be returned. Allowed options
                    are: ``nvr``, ``nevr``, ``nvra``, ``nevra``, ``n``, ``e``,
                    ``v``, ``r``, ``a``. If arch is not present in ``rpmstr``
                    but requested in ``fmt``, ``noarch`` is used. Epoch is
                    provided only when specifically requested (e.g.
                    ``fmt='nevr'``) **and** being non-zero; otherwise it's
                    supressed (the only exception is ``fmt='e'``, where you
                    receive ``0`` for zero epoch).
    :param bool end_arch: set this to ``True`` if ``rpmstr`` ends with an
                          architecture identifier (``foo-1.2-3.fc20.x86_64``).
                          It's not possible to reliably distinguish that case
                          automatically.
    :return: string based on the specified format, or integer if ``fmt='e'``
    :raise CheckbValueError: if ``fmt`` value is not supported
    '''
    fmt = fmt.lower()
    supported_formats = ['nvr', 'nevr', 'nvra', 'nevra',
                         'n', 'e', 'v', 'r', 'a']
    if fmt not in supported_formats:
        raise exc.CheckbValueError("Format '%s' not in supported formats "
                                      "(%s)" % (fmt, ', '.join(supported_formats)))

    # add arch if not present
    if not end_arch:
        rpmstr += '.noarch'

    # split rpmstr
    nevra = hawkey.split_nevra(rpmstr)

    # return simple fmt
    if len(fmt) == 1:
        return {'n': nevra.name,
                'e': nevra.epoch,
                'v': nevra.version,
                'r': nevra.release,
                'a': nevra.arch}[fmt]

    # return complex fmt
    evr = nevra.evr()
    # supress epoch if appropriate
    if 'e' not in fmt or nevra.epoch == 0:
        evr = evr[evr.find(':')+1:]  # remove 'epoch:' from the beginning

    result = '%s-%s' % (nevra.name, evr)

    # append arch if requested
    if 'a' in fmt:
        result += '.' + nevra.arch

    return result


def cmpNEVR(nevr1, nevr2):
    '''Compare two RPM version identifiers in NEVR format.

    :param str nevr1: RPM identifier in N(E)VR format
    :param str nevr2: RPM identifier in N(E)VR format
    :return: ``-1``/``0``/``1`` if ``nevr1 < nevr2`` / ``nevr1 == nevr2`` /
             ``nevr1 > nevr2``
    :rtype: int
    :raise CheckbValueError: if name in ``nevr1`` doesn't match name in
                                ``nevr2``
    '''
    rpmver1 = hawkey.split_nevra(nevr1 + '.noarch')
    rpmver2 = hawkey.split_nevra(nevr2 + '.noarch')

    if rpmver1.name != rpmver2.name:
        raise exc.CheckbValueError("Name in nevr1 doesn't match name in "
                                      "nevr2: %s, %s" % (nevr1, nevr2))

    # sack is needed for the comparison, because it can be influence the
    # comparison (for example epoch can be set to be ignored). A default empty
    # sack should match Fedora customs
    sack = hawkey.Sack()

    # we need evr_cmp to return int so we can use it as comparison function
    # in python's sorted
    return int(rpmver1.evr_cmp(rpmver2, sack))


sortkeyNEVR = functools.cmp_to_key(cmpNEVR)


def install(pkgs):
    '''Install packages from system repositories using DNF. Either root or sudo access required.

    :param pkgs: packages to be installed, e.g. ``['pidgin']``, or any other argument supported by
                 ``dnf install`` command
    :type pkgs: list of str
    :raise CheckbPermissionError: if we don't have permissions to run DNF as admin
    :raise CheckbError: if DNF return code is not zero
    '''
    if not pkgs:
        return

    log.info('Installing %d packages...', len(pkgs))
    pkglist = ' '.join([pipes.quote(pkg) for pkg in pkgs])

    if not os_utils.is_root() and not os_utils.has_sudo():
        raise exc.CheckbPermissionError("Can't install packages without root or sudo access. "
                                           'Packages requested: %s' % pkglist)

    cmd = ['dnf', '--assumeyes', 'install']
    cmd.extend(pkgs)

    if not os_utils.is_root():  # we must have sudo at this point, don't test again needlessly
        cmd = ['sudo', '--non-interactive'] + cmd

    log.debug('Running: %s', ' '.join([pipes.quote(c) for c in cmd]))
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        log.error(u'✘ Package installation failed. We tried to install following packages:\n%s'
                  '\nDNF returned exit code %d and output:\n%s', pkglist, e.returncode,
                  e.output.rstrip())
        raise exc.CheckbError("Unable to install packages: %s" % pkglist)
    else:
        log.debug(u'✔ Package installation completed successfully. DNF output was:\n%s',
                  output.rstrip())
        return


def get_dist_tag(rpmstr):
    '''Parse disttag from an RPM package version string.

    :param str rpmstr: string to be manipulated in a format of N(E)VR
                       (``foo-1.2-3.fc20`` or ``bar-4:1.2-3.fc20``) or N(E)VRA
                       (``foo-1.2-3.fc20.x86_64`` or ``bar-4:1.2-3.fc20.i686``)
    :return: string containing dist tag (``fc20``)
    :raise CheckbValueError: if ``rpmstr`` does not contain dist tag
    '''

    release = rpmformat(rpmstr, 'r')
    matches = re.findall(r'\.(fc\d{1,2})\.?', release)
    if not matches:
        raise exc.CheckbValueError('Could not parse disttag from %s' % rpmstr)

    # there might be e.g. fc22 in git commit hash as part of the release,
    # so just take the last match which should be disttag
    return matches[-1]
