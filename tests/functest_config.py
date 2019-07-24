# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Functional tests for checkb/config.py'''

import os
import pytest

from checkb import config


@pytest.mark.usefixtures('unset_profile', 'disable_create_dirs')
class TestConfig(object):

    @pytest.fixture
    def unset_profile(self, monkeypatch):
        '''Unset the profile environment variable

        For majority of our test suite we want to use TestingConfig, because
        it's faster. But here, in functional tests for Config, we want to use
        other profiles sometimes, because then we can test the code paths that
        deal with real files.
        '''
        monkeypatch.delenv(config.PROFILE_VAR)

    @pytest.fixture
    def disable_create_dirs(self, monkeypatch):
        '''Disable _create_dirs() method'''
        monkeypatch.setattr(config, '_create_dirs', lambda x: None)

    @pytest.fixture
    def tmpconffile(self, tmpdir, monkeypatch):
        '''Create a temporary file as the config file and set up CONF_DIRS and
        CONF_FILE appropriately, so that only this file gets loaded.

        @return conf file instance (py.path.local object)
        '''
        conf_file = tmpdir.join('test_conf.yaml')
        monkeypatch.setattr(config, 'CONF_DIRS',
                            [os.path.dirname(conf_file.strpath)])
        monkeypatch.setattr(config, 'CONF_FILE',
                            os.path.basename(conf_file.strpath))
        return conf_file

    def teardown_method(self, method):
        '''Run this after every test method execution ends'''
        # reset the singleton instance back
        config._config = None

    def setup_method(self, method):
        '''Run this before every test method execution start'''
        # make sure singleton instance is empty
        config._config = None


    def test_devel_profile_empty_config(self, tmpconffile):
        '''Empty file and no envvar should return development profile'''
        # create an empty config file
        tmpconffile.write('# just a comment')

        conf = config.get_config()
        assert conf.profile == config.ProfileName.DEVELOPMENT

    def test_profile_override_in_conf(self, tmpconffile):
        '''No envvar and something specified in config file should respect
        the config file choice'''
        # set a profile in config file
        tmpconffile.write('profile: %s' % config.ProfileName.PRODUCTION)

        conf = config.get_config()
        assert conf.profile == config.ProfileName.PRODUCTION

    def test_profile_envvar(self, monkeypatch, tmpconffile):
        '''If both envvar and config profile are specified, envvar should have
        the preference'''
        # set a profile in envvar
        monkeypatch.setenv(config.PROFILE_VAR, config.ProfileName.PRODUCTION)
        # set a profile in config file
        tmpconffile.write('profile: %s' % config.ProfileName.DEVELOPMENT)

        conf = config.get_config()
        assert conf.profile == config.ProfileName.PRODUCTION

    def test_conf_file_override(self, monkeypatch, tmpconffile):
        '''Even if both envvar and config profile are specified, we should still
        respect config file option values'''
        # set a profile in envvar
        monkeypatch.setenv(config.PROFILE_VAR, config.ProfileName.PRODUCTION)
        # set a profile in config file
        tmpconffile.write('''
profile: %s
cachedir: /some/path
'''     % config.ProfileName.DEVELOPMENT)

        conf = config.get_config()
        assert conf.cachedir == '/some/path'
        assert conf.cachedir != config.ProductionConfig().cachedir

    def test_search_dirs_first(self, monkeypatch, tmpdir):
        '''Test if _search_dirs returns first found config file if more of them
        exist in searched paths'''
        conf_file1 = tmpdir.mkdir('dir1').join('test.yaml')
        conf_file2 = tmpdir.mkdir('dir2').join('test.yaml')
        conf_file1.write('')
        conf_file2.write('')

        conf_file = config._search_dirs(
            (conf_file1.dirname, conf_file2.dirname), 'test.yaml')
        assert conf_file == conf_file1.strpath

        conf_file = config._search_dirs(
            (conf_file2.dirname, conf_file1.dirname), 'test.yaml')
        assert conf_file == conf_file2.strpath
