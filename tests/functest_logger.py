# -*- coding: utf-8 -*-
# Copyright 2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import os
import logging
import pytest

from checkb import logger
from checkb import config


@pytest.mark.usefixtures('setup')
class TestLogger():

    @pytest.fixture
    def setup(self, monkeypatch):
        '''Run before every method'''
        conf = config.get_config()
        monkeypatch.setattr(conf, 'log_file_enabled', True)
        # remember the list of root handlers
        self.root_handlers = logging.getLogger().handlers
        # remember the level of the stream handler
        self.stream_level = (logger.stream_handler.level if logger.stream_handler
                             else None)

    def teardown_method(self, method):
        '''Run after every method'''
        # reset the list of root handlers
        logging.getLogger().handlers = self.root_handlers
        # reset the stream handler level
        if logger.stream_handler:
            logger.stream_handler.setLevel(self.stream_level)
        # reset memory buffer in case we run this test several times in a row
        logger.mem_handler.buffer = []

    def test_logfile(self, tmpdir):
        '''Messages should be logged to file when enabled'''
        log_path = tmpdir.join('test.log').strpath

        logger.init()
        fh = logger.add_filehandler(filelog_path=log_path)
        msg = 'This should appear in the log file'
        logger.log.debug(msg)
        fh.flush()

        with open(log_path) as log_file:
            lines = log_file.readlines()

        assert msg in lines[-1]

    def test_logfile_no_write(self, tmpdir):
        '''If file log is not writeable, an exception should be raised'''
        log_file = tmpdir.join('test.log')
        log_path = log_file.strpath
        log_file.write('')
        # make the file inaccessible for writing
        os.chmod(log_path, 0)

        logger.init()
        with pytest.raises(IOError):
            logger.add_filehandler(filelog_path=log_path)

    def test_memhandler_to_logfile_level(self, tmpdir):
        '''When forwarding messages from memory to file, only messages with
        appropriate levels should be passed over'''
        log_path = tmpdir.join('test.log').strpath
        logger.init_prior_config()

        # include random strings in the message for better reliability
        msg1 = 'A debug message Xai(Deihee8a'
        logger.log.debug(msg1)
        msg2 = 'An info message aC2pu}i5chai'
        logger.log.info(msg2)
        msg3 = 'A warn message lai_choow5Ie'
        logger.log.warning(msg3)

        logger.init()
        fh = logger.add_filehandler(filelog_path=log_path, level_file=logging.WARN)
        fh.flush()

        with open(log_path) as log_file:
            lines = log_file.readlines()

        # msg1 nor msg2 should not be there, msg3 should be there
        assert len([line for line in lines if msg1 in line]) == 0
        assert len([line for line in lines if msg2 in line]) == 0
        assert len([line for line in lines if msg3 in line]) == 1
