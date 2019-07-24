# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Unit tests for checkb/config.py'''

from __future__ import print_function
import os
import sys
import pytest
import mock
from io import StringIO

from checkb import config
from checkb import exceptions as exc


PYVER = sys.version_info.major
builtin_open = '__builtin__.open' if PYVER < 3 else 'builtins.open'


@pytest.mark.usefixtures('setup')
class TestConfig(object):

    @pytest.fixture
    def setup(self, monkeypatch):
        '''Run this before every test invocation'''
        monkeypatch.setattr(config, '_config', None)

    def unset_profile(self, monkeypatch):
        '''Unset the profile environment variable

        For majority of our test suite we want to use TestingConfig, because
        it's faster. But here, in functional tests for Config, we want to use
        other profiles sometimes, because then we can test the code paths that
        deal with real files.
        '''
        monkeypatch.delenv(config.PROFILE_VAR)

    def disable_create_dirs(self, monkeypatch):
        '''Disable _create_dirs() method'''
        monkeypatch.setattr(config, '_create_dirs', lambda x: None)

    def test_testing_profile(self):
        '''By default we should have a testing profile'''
        assert os.getenv(config.PROFILE_VAR) == config.ProfileName.TESTING
        conf = config.get_config()
        print(conf)
        assert conf.profile == config.ProfileName.TESTING
        assert isinstance(conf, config.TestingConfig)

    def test_singleton_instance(self):
        '''Test whether we really have a singleton Config instance'''
        conf = config.get_config()
        assert isinstance(conf, config.Config)
        assert conf is config._config
        conf2 = config.get_config()
        assert conf2 is conf

    def test_load_defaults(self):
        '''Test _load_defaults() function'''
        for attr, value in vars(config.ProfileName).items():
            print(attr, value)
            if attr.startswith('_'):
                continue
            conf = config._load_defaults(value)
            assert conf.profile == value

    def test_load_defaults_invalid_name(self):
        '''Should crash for invalid profile name'''
        with pytest.raises(exc.CheckbConfigError):
            config._load_defaults('invalid profile name')

    def test_load_file_empty(self):
        '''Test _load_file() function with empty file'''
        contents = StringIO(u'')
        conf_object = config._load_file(contents)
        assert conf_object == {}

    def test_load_file_commented(self):
        '''Test _load_file() function with fully commented out file'''
        contents = StringIO(u'''
# first commented line
# second: line
# last line
        ''')
        conf_object = config._load_file(contents)
        assert conf_object == {}

    def test_load_file_options(self):
        '''Test _load_file() function with some options present'''
        contents = StringIO(u'''# a header comment
option1: value1
# option2: value2
option3: 15
option4: ''
option5: False''')
        conf_object = config._load_file(contents)
        assert {'option1': 'value1',
                'option3': 15,
                'option4': '',
                'option5': False} == conf_object

    def test_load_file_invalid_syntax(self):
        '''Test _load_file() function with invalid syntax'''
        with pytest.raises(exc.CheckbConfigError):
            contents = StringIO(u'a single string (not dict)')
            config._load_file(contents)

        with pytest.raises(exc.CheckbConfigError):
            contents = StringIO(u'tab:\t #this is invalid in YAML')
            config._load_file(contents)

    def test_load_file_invalid_type(self):
        '''Test _load_file() function with invalid option type'''
        # tmpdir is string, with string it should pass
        contents = StringIO(u'tmpdir: foo')
        config._load_file(contents)

        # but with anything else, it should fail
        with pytest.raises(exc.CheckbConfigError):
            contents = StringIO(u'tmpdir: False')
            config._load_file(contents)

    def test_merge_config(self):
        '''Test _merge_config() function'''
        conf = config.get_config()
        # let's try to override 'tmpdir'
        # the only exception is 'profile', it must not be overridden
        assert hasattr(conf, 'tmpdir')
        assert hasattr(conf, 'profile')
        old_profile = conf.profile
        file_config = {'tmpdir': '/a/road/to/nowhere',
                       'profile': 'invalid'}
        config._merge_config(conf, file_config)
        assert conf.tmpdir == '/a/road/to/nowhere'
        assert conf.profile == old_profile

    def test_no_load_config(self, monkeypatch):
        '''We shouldn't load config files in the testing profile'''
        # we will do that by checking that appropriate disk-touching methods
        # don't get called
        def _search_dirs_raise(x, y):
            assert False, 'This must not be called'

        def _load_file_raise(x):
            assert False, 'This must not be called'

        monkeypatch.setattr(config, '_search_dirs', _search_dirs_raise)
        monkeypatch.setattr(config, '_load_file', _load_file_raise)

        conf = config.get_config()
        assert isinstance(conf, config.Config)

    def test_devel_profile_no_config(self, monkeypatch):
        '''When there are no config files and no envvar, the profile should be
        set to 'development' '''
        self.unset_profile(monkeypatch)
        self.disable_create_dirs(monkeypatch)
        # make sure we don't find any config files
        monkeypatch.setattr(config, 'CONF_DIRS', [])
        conf = config.get_config()
        assert conf.profile == config.ProfileName.DEVELOPMENT

    def test_check_sanity_runtask_mode(self):
        '''Should crash for unknown runtask mode names'''
        conf = config.get_config()

        for attr, value in vars(config.RuntaskModeName).items():
            if attr.startswith('_'):
                continue
            conf.runtask_mode = value
            config._check_sanity(conf)

        conf.runtask_mode = 'invalid runtask mode name'
        with pytest.raises(exc.CheckbConfigError):
            config._check_sanity(conf)

    def test_check_yaml_scanning_error(self):
        file_data = '%'
        mocked_open = mock.mock_open(read_data=file_data)

        with mock.patch(builtin_open, mocked_open):
            with pytest.raises(exc.CheckbConfigError):
                config.parse_yaml_from_file('mocked_filename')

    def test_check_yaml_parsing_error(self):
        file_data = ':'
        mocked_open = mock.mock_open(read_data=file_data)

        with mock.patch(builtin_open, mocked_open):
            with pytest.raises(exc.CheckbConfigError):
                config.parse_yaml_from_file('mocked_filename')


class TestConfigDefaults(object):

    configtypes = [config.Config(),
                   config.TestingConfig(),
                   config.ProductionConfig()
                   ]

    @pytest.fixture(params=configtypes)
    def getconfig(self, request):
        return request.param

    def test_no_null_defaults(self, getconfig):
        for option in dir(getconfig):
            if option.startswith('_'):
                continue
            assert getattr(getconfig, option) is not None
