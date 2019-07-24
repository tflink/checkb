# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''py.test configuration and plugins
Read more at: http://pytest.org/latest/plugins.html#conftest-py-plugins'''

import os
import logging

import checkb.logger
import checkb.config
import checkb.config_defaults


def pytest_addoption(parser):
    """
    Add an option to the py.test parser to detect when the functional tests
    should be detected and run
    """

    parser.addoption('-F', '--functional', action='store_true', default=False,
                     help='Add functional tests')


def pytest_ignore_collect(path, config):
    """Prevents collection of any files named functest* to speed up non
        integration tests"""
    if path.fnmatch('*functest*'):
        try:
            is_functional = config.getvalue('functional')
        except KeyError:
            return True

        return not is_functional


def pytest_configure(config):
    """Called after command line options have been parsed and all plugins and
    initial conftest files been loaded."""

    # set a testing config profile
    os.environ[checkb.config.PROFILE_VAR] = \
        checkb.config.ProfileName.TESTING

    # enable debug logging for checkb
    # This will allow us to use checkb-logged output for failed tests.
    # You can also use "py.test -s" option to see all output even for passed
    # tests (of course, it's better to run the suite with just a single file
    # rather than the whole directory in this case)
    checkb.logger.init_prior_config()
    # and this will show debug messages from many other libraries as well
    logging.getLogger().setLevel(logging.NOTSET)
    # always use full formatter format
    checkb.logger.stream_handler.setFormatter(checkb.logger._formatter_full)

    # load config files from a testing conf dir (default config files might
    # not be available and we can't rely on their contents)
    checkb.config.CONF_DIRS = [
        os.path.abspath(os.path.dirname(__file__) + '/conf')
    ]
