# -*- coding: utf-8 -*-
# Copyright 2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import logging

from checkb import logger
from checkb import config


class TestLogger():

    def setup_method(self, method):
        '''Run before every method'''
        # remember the list of root handlers
        self.root_handlers = logging.getLogger().handlers
        # remember the level of the stream handler
        self.stream_level = (logger.stream_handler.level if logger.stream_handler
                             else None)
        # remember the level of default checkb logger
        self.log_level = logger.log.level

    def teardown_method(self, method):
        '''Run after every method'''
        # reset the list of root handlers
        logging.getLogger().handlers = self.root_handlers
        # reset the stream handler level
        if logger.stream_handler:
            logger.stream_handler.setLevel(self.stream_level)
        # reset the level of the default checkb logger
        logger.log.setLevel(self.log_level)

    def test_logging_messages(self, capfd):
        '''Basic message logging functionality'''
        msg = 'Quo vadis?'
        logger.log.info(msg)
        out, err = capfd.readouterr()
        assert not out
        assert msg in err

    def test_levels(self, capfd):
        '''Messages with lower level than set should be ignored, others included'''
        logger.log.setLevel(logging.WARNING)

        # ignore this message
        msg = 'Quo vadis?'
        logger.log.info(msg)
        out, err = capfd.readouterr()
        assert not out
        assert not err

        # include this message
        msg = 'Whither goest thou?'
        logger.log.warning(msg)
        out, err = capfd.readouterr()
        assert not out
        assert msg in err

    def test_no_syslog(self):
        '''Syslog should be disabled under testing profile'''
        logger.init()
        root = logging.getLogger()

        msg = ('If this failed, it means we need either set syslog=False'
               'as default in logger.init(), or we need to '
               'introduce new variables in Config to make sure syslog is '
               'disabled during the test suite.')

        if logger.syslog_handler is not None:
            assert logger.syslog_handler not in root.handlers, msg

    def test_override_level(self, monkeypatch):
        '''A log level from config file should be correctly applied'''
        conf = config.get_config()
        monkeypatch.setattr(conf, 'log_level_stream', 'CRITICAL')
        logger.init()
        assert logging.getLevelName(logger.stream_handler.level) == 'CRITICAL'

    def test_invalid_level(self, monkeypatch):
        '''Invalid log level in config file should be reverted to default'''
        conf = config.get_config()
        default_level = conf.log_level_stream

        monkeypatch.setattr(conf, 'log_level_stream', 'INVALID')
        logger.init()
        assert logging.getLevelName(logger.stream_handler.level) != 'INVALID'
        assert logging.getLevelName(logger.stream_handler.level) == default_level

    def test_memhandler(self, monkeypatch):
        '''Records should be stored in memhandler between init_prior_config()
        and init(), regardless of chosen stream level'''
        logger.init_prior_config(level_stream=logging.WARN)

        msg = 'Some initialization message'
        logger.log.debug(msg)

        assert logger.mem_handler.buffer[-1].getMessage() == msg
