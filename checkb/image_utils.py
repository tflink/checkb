# -*- coding: utf-8 -*-
# Copyright 2009-2017, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

from __future__ import absolute_import

import re

from checkb import exceptions as exc
from checkb.logger import log
from checkb import config

try:
    from checkb.ext.fedora import rpm_utils
except ImportError as e:
    raise exc.CheckbImportError(e)


def devise_environment(arg_data, playbook_vars):
    '''Takes an input item and type, and returns a required run-environment,
    or a default one, if the task doesn't require anything specific.

    :param dict arg_data: parsed command-line arguments (item, type and arch
        are used in this method)
    :param dict playbook_vars: vars dict created by
        :meth:`executor._create_playbook_vars`
    :return: dict containing ``distro``, ``release``, ``flavor`` and ``arch``.
        Each either set, or ``None``.
    '''

    env = {'distro': None, 'release': None, 'flavor': None, 'arch': None}

    item = arg_data['item']
    item_type = arg_data['type']
    arch = arg_data['arch']

    if playbook_vars['checkb_match_host_distro']:
        if item_type == 'koji_build':
            # FIXME: find a way to make this not Fedora-specific
            # For `xchat-2.8.8-21.fc20` disttag is `fc20` for example
            try:
                distro = rpm_utils.get_dist_tag(item)[:2]
                env['distro'] = {'fc': 'fedora'}.get(distro)
            except exc.CheckbValueError:
                log.debug('Failed to parse distro from koji build %s, using '
                    'default', item)

        elif item_type == 'koji_tag':
            if re.match(r'^f[0-9]{2}-.*', item):
                env['distro'] = 'fedora'

    if playbook_vars['checkb_match_host_release']:
        if item_type == 'koji_build':
            # FIXME: find a way to make this not Fedora-specific
            # Last two characters in rpm's disttag are the Fedora release.
            # For `xchat-2.8.8-21.fc20` disttag is `fc20` for example
            try:
                env['release'] = rpm_utils.get_dist_tag(item)[-2:]
            except exc.CheckbValueError:
                log.debug('Failed to parse release from koji build %s, using '
                    'default', item)

        elif item_type == 'koji_tag':
            if re.match(r'^f[0-9]{2}-.*', item):
                env['release'] = item[1:3]

    if playbook_vars['checkb_match_host_arch']:
        if arch != 'noarch':
            env['arch'] = arch

    log.debug('Forced environment values: %s', env)

    env['distro'] = env['distro'] or config.get_config().default_disposable_distro
    env['release'] = env['release'] or config.get_config().default_disposable_release
    env['flavor'] = env['flavor'] or config.get_config().default_disposable_flavor
    env['arch'] = env['arch'] or config.get_config().default_disposable_arch

    log.debug('Environment to be used: %s', env)

    return env
