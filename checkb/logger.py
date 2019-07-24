# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

''' Configure logging in checkb.

There are two modes how to operate - as an external library, or as the main
script runner:

* In the external library mode, we try not to change any global defaults, not
  touch the root logger, and not attach any handlers. The main script author
  should be in control of all these things.
* In the main script runner mode, we control everything - we configure the root
  logger, attach handlers to it, and set verbosity of this and any other library
  as we see fit.
'''

from __future__ import absolute_import
import sys
import os
import logging
import logging.handlers
import traceback
import time
import getpass
# you must not import checkb.config here because of cyclic dependencies

# http://docs.python.org/2/howto/logging.html#configuring-logging-for-a-library
#: the main logger for checkb library, easily accessible from all our
#: modules
log = logging.getLogger('checkb')
log.addHandler(logging.NullHandler())  # this is needed when running in library mode

# log formatting
_fmt_full = '[%(name)s:%(filename)s:%(lineno)d] '\
            '%(asctime)s %(levelname)-7s %(message)s'
_fmt_simple = '[%(name)s] %(asctime)s %(levelname)-7s %(message)s'
_datefmt_full = '%Y-%m-%d %H:%M:%S'
_datefmt_simple = '%H:%M:%S'
_formatter_full = logging.Formatter(fmt=_fmt_full, datefmt=_datefmt_full)
_formatter_simple = logging.Formatter(fmt=_fmt_simple, datefmt=_datefmt_simple)
# set logging time to UTC/GMT
_formatter_full.converter = time.gmtime
_formatter_simple.converter = time.gmtime

#: our current stream handler sending logged messages to stderr
stream_handler = None

#: our current syslog handler sending logged messages to syslog
syslog_handler = None

#: our current memory handler sending logged messages to memory
#: log prior to creating file log (after its creation, content
#: of the memory log is flushed into the file log)
mem_handler = None


def _create_handlers(syslog=False):
    '''Create stream, syslog and memory handlers. This should be called
    before any method tries to operate on handlers. Handlers are created
    only if they don't exist yet (they are `None`), otherwise they are
    skipped. So this method can easily be called multiple times.

    Note: Handlers can't be created during module import, because that breaks
    stream capturing functionality when running through ``pytest``.

    :param bool syslog: create syslog handler. Syslog must be available.
    :raise socket.error: if syslog handler creation failed
    '''
    global stream_handler, syslog_handler, mem_handler

    if not stream_handler:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(_formatter_simple)

    if syslog and not syslog_handler:
        syslog_handler = logging.handlers.SysLogHandler(address='/dev/log',
                             facility=logging.handlers.SysLogHandler.LOG_LOCAL4)

    if not mem_handler:
        mem_handler = logging.handlers.MemoryHandler(capacity=1024)
        mem_handler.setFormatter(_formatter_full)


def _log_excepthook(*exc_info):
    '''Called when an exception is not caught'''
    log.critical(''.join(traceback.format_exception(*exc_info)))


def _set_verbosity_levels():
    '''Configure checkb and other important libraries for maximum desired
    verbosity. The actual verbosity is then adjusted in our handlers. This
    should be only called when running as the main script.'''
    log.setLevel(logging.DEBUG)
    logging.getLogger('resultsdb_api').setLevel(logging.DEBUG)
    logging.getLogger('koji').setLevel(logging.INFO)
    logging.getLogger('testcloud').setLevel(logging.DEBUG)


def init_prior_config(level_stream=None):
    '''Initialize Checkb logging with default values which do not rely on
    a config file. Only stream logging is enabled here. This is used before the
    config file is loaded. After that a proper initialization should take place
    through the :func:`init` method.

    Note: Since this touches the root logger, it should be called only when
    Checkb is run as the main program (through its runner), not when it is
    used as a library.

    :param int level_stream: message level of the stream logger. The level
        definitions are in :mod:`logging`. If ``None``, the default level is
        used (i.e. :data:`logging.NOTSET`).
    '''
    _create_handlers()
    _set_verbosity_levels()

    if level_stream is not None:
        stream_handler.setLevel(level_stream)

    rootlogger = logging.getLogger()
    rootlogger.addHandler(stream_handler)
    rootlogger.addHandler(mem_handler)

    sys.excepthook = _log_excepthook


def _set_level(handler, level, conf_name):
    '''Set logging level to a handler. Fall back to config defaults if the level
    name is invalid.

    :param handler: log handler to configure
    :type handler: instance of :class:`logging.Handler`
    :param level: level identification from :mod:`logging`
    :type level: ``str`` or ``int``
    :param str conf_name: the name of the configuration option of the default
        level for this handler. If ``level`` value is invalid, it will retrieve
        the default value from the config file and set it instead.
    '''
    from checkb import config
    try:
        handler.setLevel(level)
    except ValueError:
        conf_defaults = config._load_defaults(config.get_config().profile)
        default_level = getattr(conf_defaults, conf_name)
        log.warning("Invalid logging level '%s' for '%s'. Resetting to default "
                    "value '%s'.", level, conf_name, default_level)
        handler.setLevel(default_level)


def init(level_stream=None, stream=True, syslog=False):
    """Initialize Checkb logging.

    Note: Since this touches the root logger, it should be called only when
    Checkb is run as the main program (through its runner), not when it is
    used as a library.

    :param int level_stream: level of stream logging as defined in
        :mod:`logging`. If ``None``, a default level from config file is used.
    :param bool stream: enable logging to process stream (stderr)
    :param bool syslog: enable logging to syslog
    """

    # We import checkb.config here because import from beginning
    # of this module causes problems with cyclic dependencies
    from checkb import config
    conf = config.get_config()

    if level_stream is None:
        level_stream = conf.log_level_stream

    _create_handlers()
    rootlogger = logging.getLogger()
    sys.excepthook = _log_excepthook

    if stream:
        _set_level(stream_handler, level_stream, "log_level_stream")
        if stream_handler.level <= logging.DEBUG:
            stream_handler.setFormatter(_formatter_full)
        rootlogger.addHandler(stream_handler)
        log.debug("Stream logging enabled with level: %s",
                  logging.getLevelName(stream_handler.level))
    else:
        rootlogger.removeHandler(stream_handler)

    if syslog:
        _create_handlers(syslog=True)
        rootlogger.addHandler(syslog_handler)
        log.debug("Syslog logging enabled with level: %s",
                  logging.getLevelName(syslog_handler.level))
    else:
        rootlogger.removeHandler(syslog_handler)

    add_filehandler()


def add_filehandler(level_file=None, filelog_path=None):
    """
    Add a file handler.

    :param int level_file: level of file logging as defined in
        :mod:`logging`. If ``None``, a default level from config file is used.
    :param str filelog_path: path to the log file. If ``None``, the value is
        loaded from config file, and it is only used when file logging is
        enabled in the config file (otherwise nothing happens).
    :returns: created file handler or ``None`` if logging was not enabled in
        the config file
    :raise IOError: if log file can't be opened for writing
    """
    # We import checkb.config here because import from beginning
    # of this module causes problems with cyclic dependencies
    from checkb import config
    conf = config.get_config()
    rootlogger = logging.getLogger()
    universal_logfile = not filelog_path  # an overall log file for all runs

    if universal_logfile and not conf.log_file_enabled:
        return

    if level_file is None:
        level_file = conf.log_level_file

    if universal_logfile:
        filelog_path = os.path.join(conf.logdir, 'checkb-%s.log' % getpass.getuser())

    file_handler = logging.FileHandler(filelog_path, encoding='UTF-8')
    file_handler.setFormatter(_formatter_full)

    # try access
    try:
        f = open(filelog_path, 'a')
        if universal_logfile:
            # since we have the file opened at the moment, put a separator
            # into it, it will help to differentiate between different task
            # runs
            f.write('#'*120 + '\n')
        f.close()
    except IOError as e:
        log.error("Log file can't be opened for writing: %s\n  %s", filelog_path, e)
        raise

    _set_level(file_handler, level_file, "log_level_file")

    # forward all 'missed' messages from memory to file
    # there's a method for automatically forwarding all messages from a
    #  memory handler, but it does not respect target handler logging level.
    # we need to do it manually
    for record in mem_handler.buffer:
        if record.levelno >= file_handler.level:
            file_handler.handle(record)

    rootlogger.addHandler(file_handler)

    log.debug('File logging enabled with level %s into: %s',
              logging.getLevelName(file_handler.level), filelog_path)

    return file_handler


def remove_mem_handler():
    '''After adding last file handler, the memory handler is no longer needed
    and you should call this to have it removed and avoid filling the memory
    buffer with all log messages'''
    rootlogger = logging.getLogger()
    mem_handler.close()
    rootlogger.removeHandler(mem_handler)
