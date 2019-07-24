# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Global configuration for checkb and relevant helper methods.'''

from __future__ import absolute_import
import os
import yaml
import getpass
import sys

if (sys.version_info >= (3, 3)):
    import collections.abc as abc
else:
    import collections as abc


import checkb
from checkb import exceptions as exc
from checkb.logger import log
from checkb.config_defaults import (Config, ProductionConfig, TestingConfig, ProfileName,
                                    RuntaskModeName)
from checkb import file_utils
from checkb.python_utils import basestring

CONF_DIRS = [ # local checkout dir first, then system wide dir
    os.path.abspath(os.path.dirname(checkb.__file__) + '/../conf'),
    '/etc/checkb']
'''A list of directories where config files are stored. The config files are
loaded from these locations in the specified order, and only the first config
file found is used (further locations are ignored). The first location is
dynamic, relative to the package location and it reflects the usual config
location in a git checkout.'''

CONF_FILE = 'checkb.yaml'
'''the name of our configuration file'''

NS_CONF_FILE = 'namespaces.yaml'
'''the name of result namespaces configuration file'''

PROFILE_VAR = 'CHECKB_PROFILE'
'''environment variable name for setting config profile'''

_config = None
'''a singleton instance of Config'''


def get_config():
    '''Get the Config instance. This method is implemented using the singleton
    pattern - you will always receive the same instance, which will get
    auto-initialized on the first method call.

    :return: either :class:`.Config` or its subclass, depending on checkb
             profile used.
    :raise CheckbConfigError: if config file parsing and handling failed
    '''

    global _config
    if not _config:
        _config = _get_instance()
    return _config


def _get_instance():
    '''Do everything necessary to fully initialize Config instance, update it
    with external configuration, make all final touches.

    :return: :class:`.Config` instance ready to be used
    :raise CheckbConfigError: if file config parsing and handling failed
    '''
    config = _load()
    _check_sanity(config)
    log.debug('Using config profile: %s', config.profile)

    # make sure required directories exist
    _create_dirs(config)

    return config


def _load():
    '''Load the configuration, internal (defaults) and external (config files)

    :return: :class:`.Config` instance that was updated by external config file
             contents
    :raise CheckbConfigError: if file config parsing and handling failed
    '''

    # first load the defaults and make sure we even want to load config files
    env_profile = os.getenv(PROFILE_VAR)
    config = _load_defaults(env_profile)
    if config.profile == ProfileName.TESTING:
        log.debug('Testing profile, not loading config files from disk')
        _customize_values(config)
        return config

    # load config files
    filename = _search_dirs(CONF_DIRS, CONF_FILE)
    if not filename:
        log.warning(
            'No config file %s found in dirs: %s' % (CONF_FILE, CONF_DIRS))
        return config

    log.debug('Using config file: %s', filename)
    file_config = _load_file(filename)
    file_profile = file_config.get('profile', None)

    # reload the config defaults if the profile was specified in the config file
    # (and not present in env variable)
    if file_profile and not env_profile:
        config = _load_defaults(file_profile)

    # merge the changes from the config file
    _merge_config(config, file_config)

    # do additional values customization
    _customize_values(config)

    # set config filename used, this is set after merging
    # so it doesn't get overridden
    config._config_filename = filename

    return config


def _check_sanity(config):
    '''Check important config keys for sane/allowed values. Raise exception
    if config file is not correct.

    :param config: :class:`.Config` instance
    :raise CheckbConfigError: when important config key has invalid value
    '''

    # runtask_mode value must be from its enum
    if config.runtask_mode not in [RuntaskModeName.LOCAL, RuntaskModeName.LIBVIRT]:
        raise exc.CheckbConfigError('Invalid runtask mode name: %s' % config.runtask_mode)


def _load_defaults(profile):
    '''Load and return Config (or its subclass) based on chosen profile.

    :param str profile: profile name as defined in :class:`.ProfileName`
    :return: :class:`.Config` instance or its subclass
    :raise CheckbConfigError: if unknown profile name is requested
    '''

    if profile == ProfileName.PRODUCTION:
        return ProductionConfig()
    elif profile == ProfileName.TESTING:
        return TestingConfig()
    elif profile == ProfileName.DEVELOPMENT or not profile:
        # the default is the development profile
        return Config()
    else:
        raise exc.CheckbConfigError('Invalid profile name: %s' % profile)


def _search_dirs(conf_dirs, conf_file):
    '''Find the configuration file in a set of directories. The first match
    is returned.

    :param conf_dirs: a list of directories to search through
    :type conf_dirs: list of str
    :param str conf_file: configuration file name
    :return: full path to the configuration file (string) or ``None`` if not
             found
    '''

    for conf_dir in conf_dirs:
        filename = os.path.join(conf_dir, conf_file)
        if os.access(filename, os.R_OK):
            return filename


def _load_file(conf_file):
    '''Parse a configuration file and return it as a dictionary. The option
    values are checked for type correctness against a default Config object.

    :param conf_file: file path (string) or file handler to the configuration
                      file in YAML syntax
    :return: dictionary parsed from the configuration file
    :raise CheckbConfigError: if any problem occurs during the parsing or
                                 some values have incorrect variable type
    '''

    # convert file path to file handle if needed
    if isinstance(conf_file, basestring):
        try:
            conf_file = open(conf_file)
        except IOError as e:
            log.exception('Could not open config file: %s', conf_file)
            raise exc.CheckbConfigError(e)

    filename = (conf_file.name if hasattr(conf_file, 'name') else
                '<unnamed file>')
    try:
        conf_obj = yaml.safe_load(conf_file)
    except yaml.YAMLError as e:
        log.exception('Could not parse config file: %s', filename)
        raise exc.CheckbConfigError(e)

    # config file might be empty (all commented out), returning None. For
    # further processing, let's replace it with empty dict
    if conf_obj is None:
        conf_obj = {}

    # check correct types
    # we should receive a single dictionary with keyvals
    if not isinstance(conf_obj, abc.Mapping):
        raise exc.CheckbConfigError('The config file %s does not have '
        'a valid structure. Instead of a mapping, it is recognized as: %s' %
                                    (filename, type(conf_obj)))

    default_conf = Config()
    for option, value in conf_obj.items():
        # check for unknown options
        try:
            default_value = getattr(default_conf, option)
        except AttributeError:
            log.warning('Unknown option "%s" in the config file %s', option,
                        filename)
            continue

        # check for correct type
        assert default_value is not None, \
            "Default values must not be None: %s" % option
        if type(default_value) is not type(value):
            raise exc.CheckbConfigError('Option "%s" in config file %s '
                'has an invalid type. Expected: %s, Found: %s'
                                        % (option, filename, type(default_value), type(value)))

    return conf_obj


def _merge_config(config, file_config):
    '''Merge a Config object and a dictionary parsed from YAML file.

    :param config: a :class:`.Config` instance to merge into
    :param dict file_config: a dictionary parsed from YAML configuration file to
                             merge from
    :return: the same ``config`` instance, but with some attributes overwritten
             with values from ``file_config``
    :raise AttributeError: if ``file_config`` contains values that ``config``
                           doesn't have. But this shouldn't happen, because
                           :func:`_load_file` should already have checked for
                           that.
    '''

    for option, value in file_config.items():
        if option == 'profile':
            # the only option not overridden from file is 'profile', because
            # that might have been dictated by env variable which has a higher
            # priority
            continue
        if hasattr(config, option):
            setattr(config, option, value)


def _customize_values(config):
    '''Customize values, if needed, after being loaded and merged.

    :param config: :class:`.Config` instance
    '''
    # We delete tmpdir before running every task. Separate tmpdir
    # for each user so we don't delete other user's tmp files.
    config.tmpdir = os.path.join(config.tmpdir, getpass.getuser())

    # set full path to the data dir
    if not os.path.isabs(config._data_dir):
        config._data_dir = os.path.abspath(
            os.path.join(os.path.dirname(checkb.__file__),
                         config._data_dir))


def _create_dirs(config):
    '''Create directories in the local file system for appropriate config
    options, like ``tmpdir``, ``logdir``, ``cachedir``, ``artifactsdir``.

    :param config: :class:`.Config` instance
    :raise CheckbError: when directories don't exist and can't be created
    '''

    for dir_ in (config.tmpdir, config.logdir, config.artifactsdir,
                 config.cachedir):
        try:
            file_utils.makedirs(dir_)
        except OSError as e:
            raise exc.CheckbError("Failed to create required directory '%s', "
                                     "please create it manually. Caused by: %s"
                                  % (dir_, e))


def parse_yaml_from_file(filename):
    '''
    Parse given file in YAML format into a dictionary.

    :param str filename: a filename that yaml data are loaded from
    :return: dictionary constructed from the yaml document
    :raise CheckbConfigError: when YAML parsing fails
    '''
    with open(filename, 'r') as datafile:
        try:
            return yaml.safe_load(datafile.read())
        except yaml.YAMLError as e:
            raise exc.CheckbConfigError(e)


def load_namespaces_config():
    '''
    Load and parse namespaces config file into a dictionary.

    :return: dictionary constructed from the yaml document
    '''

    config = {
        'namespaces_safe': ['scratch'],
        'namespaces_whitelist': {}
    }

    if get_config().profile == ProfileName.TESTING:
        log.debug('Testing profile, not loading config files from disk')
        return config

    filename = _search_dirs(CONF_DIRS, NS_CONF_FILE)
    if filename is None:
        log.warning('Could not find namespaces config in %s. Using defaults.' %
                    ', '.join(CONF_DIRS))
        return config

    data = parse_yaml_from_file(filename)
    config.update(data)

    return config
