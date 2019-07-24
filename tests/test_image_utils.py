# -*- coding: utf-8 -*-
# Copyright 2018, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Unit tests for checkb/image_utils.py'''

import pytest

from checkb.image_utils import devise_environment
from checkb import config

class TestDeviseEnvironment:

    def setup_method(self, method):
        self.arg_data = {
            'item': 'htop-2.0.2-4.fc20',
            'type': 'koji_build',
            'arch': 'i686',
        }
        self.playbook_vars = {
            'checkb_match_host_distro': True,
            'checkb_match_host_release': True,
            'checkb_match_host_arch': True,
        }
        self.cfg = config.get_config()

    def test_koji_build(self):
        env = devise_environment(self.arg_data, self.playbook_vars)
        assert env['distro'] == 'fedora'
        assert env['release'] == '20'
        assert env['arch'] == self.arg_data['arch']

    def test_koji_tag(self):
        self.arg_data = {
            'item': 'f20-updates-pending',
            'type': 'koji_tag',
            'arch': 'i686',
        }
        env = devise_environment(self.arg_data, self.playbook_vars)
        assert env['distro'] == 'fedora'
        assert env['release'] == '20'
        assert env['arch'] == self.arg_data['arch']

    def test_unknown_distro(self):
        self.arg_data['item'] = 'htop-2.0.2-4.el7'
        env = devise_environment(self.arg_data, self.playbook_vars)
        assert env['distro'] == self.cfg.default_disposable_distro
        assert env['release'] == self.cfg.default_disposable_release
        assert env['arch'] == self.arg_data['arch']

    def test_match_host_arch_true(self):
        env = devise_environment(self.arg_data, self.playbook_vars)
        assert env['distro'] == 'fedora'
        assert env['release'] == '20'
        assert env['arch'] == self.arg_data['arch']

    def test_match_host_arch_false(self):
        self.playbook_vars['checkb_match_host_arch'] = False
        env = devise_environment(self.arg_data, self.playbook_vars)
        assert env['distro'] == 'fedora'
        assert env['release'] == '20'
        assert env['arch'] == self.cfg.default_disposable_arch

    def test_match_host_release_true(self):
        env = devise_environment(self.arg_data, self.playbook_vars)
        assert env['distro'] == 'fedora'
        assert env['release'] == '20'
        assert env['arch'] == self.arg_data['arch']

    def test_match_host_release_false(self):
        self.playbook_vars['checkb_match_host_release'] = False
        env = devise_environment(self.arg_data, self.playbook_vars)
        assert env['distro'] == 'fedora'
        assert env['release'] == self.cfg.default_disposable_release
        assert env['arch'] == self.arg_data['arch']

    @pytest.mark.parametrize('match_arch', [True, False])
    def test_noarch_to_default(self, match_arch):
        self.arg_data['arch'] = 'noarch'
        self.playbook_vars['checkb_match_host_arch'] = match_arch
        env = devise_environment(self.arg_data, self.playbook_vars)
        assert env['distro'] == 'fedora'
        assert env['release'] == '20'
        assert env['arch'] == self.cfg.default_disposable_arch

    def test_no_disttag(self):
        self.arg_data['item'] = 'htop-2.0.2-4'
        env = devise_environment(self.arg_data, self.playbook_vars)
        assert env['distro'] == 'fedora'
        assert env['release'] == self.cfg.default_disposable_release
        assert env['arch'] == self.arg_data['arch']

    def test_flavor(self):
        '''Flavor is always the default one'''
        env = devise_environment(self.arg_data, self.playbook_vars)
        assert env['flavor'] == self.cfg.default_disposable_flavor
