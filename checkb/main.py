# -*- coding: utf-8 -*-
# Copyright 2009-2015, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Main class used by the runtask runner'''

from __future__ import absolute_import
import logging
import os.path
import argparse
import datetime
import copy
import sys

import checkb
from checkb import logger
from checkb import config
from checkb import check
from checkb import file_utils
from checkb.logger import log
from checkb.executor import Executor


# this should match check.py:ReportType
ITEM_TYPE_DOCS = '''\n
Below is a list of examples of ``item`` input values for different item types:

* bodhi_update: Bodhi update ID,
                e.g. ``FEDORA-2017-04459ef8cf``
* compose: Full URL to the compose or image,
           e.g. ``http://server/Fedora-Atomic-25-20170512.0.x86_64.qcow2``
* dist_git_commit: Triplet of ``namespace/repo#commit`` from distgit,
                   e.g. ``rpms/gcc#fe7fce2ad1cbf374be1a1b99af27eff733f639a0`` or
                   ``modules/dhcp#5c6331592b6c92bf7c52a2ac735f92cb8fc11304``
* docker_image: Docker registry URL,
                e.g. ``candidate-registry.fedoraproject.org/f26/mongodb:0-1.f26docker``
* git_commit: Quadruplet of ``server/repo#branch#commit``,
              e.g. \
``https://pagure.io/rpmdeplint#refs/heads/master#080d9599f01978ad554658c6a5da1642a383b969``
* koji_build: Build NVR from Koji (without epoch, even if it exists),
              e.g. ``cups-2.2.0-9.fc25``
* koji_tag: Koji tag name,
            e.g. ``f25-updates-testing-pending``
* module_build: Triplet of ``modulename-stream-version``,
                e.g. ``nodejs-f26-20170511113257``
* pull_request: Pull request URL,
                e.g. ``https://github.com/container-images/memcached/pull/12`` or
                ``https://pagure.io/checkb/checkb-trigger/pull-request/42``
'''
# this seems to be the only way how to include it in both class documentation (the generated html
# docs) and argparse help without duplication
if __doc__:
    __doc__ += ITEM_TYPE_DOCS


def get_argparser():
    '''Get the cmdline parser for the main runner.

    :rtype: :class:`argparse.ArgumentParser`
    '''

    class CustomFormatter(argparse.ArgumentDefaultsHelpFormatter,
                          argparse.RawDescriptionHelpFormatter):
        '''Convince argparse to keep newlines in description and epilog, but use a default
        formatter for arguments.
        Source: http://stackoverflow.com/a/18462760
        '''
        pass

    parser = argparse.ArgumentParser(epilog=ITEM_TYPE_DOCS, formatter_class=CustomFormatter)
    parser.add_argument("taskdir", help="taskdir with tests.yml* playbook(s) to run")
    parser.add_argument("-a", "--arch",
                        choices=["i386", "x86_64", "armhfp", "noarch"], default='noarch',
                        help="architecture specifying the item to be checked. 'noarch' value "
                             'means an arch-independent task (if the task supports it, it can '
                             'process all archs in a single go). [default: %(default)s]')
    parser.add_argument("-i", "--item", help="item to be checked")
    parser.add_argument("-t", "--type",
                        choices=check.ReportType.list(),
                        help="type of --item argument")
    parser.add_argument("-j", "--jobid", default="-1",
                        help="optional job identifier used to render log urls")
    parser.add_argument("-d", "--debug", action="store_true",
                        help="Enable debug output "
                             "(set logging level to 'DEBUG')")
    parser.add_argument("--uuid", default=datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f"),
                        help="Unique job identifier for the execution"
                             "status tracking purposes. If unset, defaults to"
                             "current datetime in UTC")
    parser.add_argument("--local", action="store_true",
                        help="make the task run locally on this very machine (the default "
                             "behavior for development profile). This also approves any required "
                             "system-wide changes to be performed (automatic installation of "
                             "package dependencies, destructive tasks allowed, etc).")
    parser.add_argument('--libvirt', action='store_true',
                        help="make the task run remotely in a disposable client spawned using "
                             "libvirt (the default behavior for production profile).")
    parser.add_argument("--ssh", metavar='user@machine[:port]',
                        help="make the task run on a remote machine over ssh")
    parser.add_argument("--ssh-privkey", metavar="</path/to/private.key>",
                        help="path to private key for remote connections over ssh")
    parser.add_argument("--no-destroy", action="store_true",
                        help="do not destroy disposable client at the end of task execution")

    return parser


def check_args(parser, args):
    """ Check if passed args doesn't have conflicts and have proper format. In case of error, this
    function prints error message and exits the program.

    :param argparse.ArgumentParser parser: parser object used to show error message and exit the
                                           program
    :param dict args: arguments previously returned by argument parser converted to dict
    """

    if len([arg for arg in [args['local'], args['libvirt'], args['ssh']] if arg]) > 1:
        parser.error('Options --local, --libvirt and --ssh are mutually exclusive')

    if args['ssh']:
        if '@' not in args['ssh']:
            parser.error("SSH connection info not in format 'user@machine' or 'user@machine:port'")


def process_args(raw_args):
    """ Processes raw input args and converts them into specific data types that
    can be used by tasks. This includes e.g. creating new args based on
    (item, item_type) pairs, or adjusting selected architecture.

    :param dict raw_args: dictionary of raw arguments. Will not be modified.
    :returns: dict of args with appended/modified data
    """
    # do not modify the input dict
    args = copy.deepcopy(raw_args)

    # store the original unprocessed args for later use when passing it to the minion
    args['_orig_args'] = raw_args

    # process item + type
    if args['type'] in check.ReportType.list():
        args[args['type']] = args['item']

    # parse ssh
    if args['ssh']:
        args['user'], machine = args['ssh'].split('@')
        if ':' in machine:
            args['machine'], port = machine.split(':')
            args['port'] = int(port)
        else:
            args['machine'] = machine
            args['port'] = 22

    # set paths
    args['taskdir'] = os.path.abspath(args['taskdir'])
    args['artifactsdir'] = os.path.join(config.get_config().artifactsdir, args['uuid'])

    # set taskname
    args['task'] = os.path.join(args['taskdir'], 'tests.yml')

    return args


def main():
    '''Main entry point executed by runtask script'''
    # Preliminary initialization of logging, so all messages before regular
    # initialization can be logged to stream.
    logger.init_prior_config()

    log.info('Execution started at: %s',
             datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'))
    log.debug('Using checkb %s', checkb.__version__)

    # parse cmdline
    parser = get_argparser()
    args = parser.parse_args()

    check_args(parser, vars(args))
    log.debug('Parsed arguments: %s', args)
    arg_data = process_args(vars(args))

    # create artifacts directory + subdirs
    try:
        artif_subdir = os.path.join(arg_data['artifactsdir'], 'checkb')
        file_utils.makedirs(artif_subdir)
        log.info("Task artifacts will be saved in: %s", arg_data['artifactsdir'])
    except OSError:
        log.error("Can't create artifacts directory %s", artif_subdir)
        raise

    # initialize logging
    level_stream = logging.DEBUG if args.debug else None
    logger.init(level_stream=level_stream)
    logpath = os.path.join(artif_subdir, 'checkb.log')
    logger.add_filehandler(level_file=logging.DEBUG, filelog_path=logpath)
    logger.remove_mem_handler()

    # start execution
    executor = Executor(arg_data)
    success = executor.execute()

    # finalize
    log.info('Task artifacts were saved in: %s', arg_data['artifactsdir'])
    if config.get_config().profile == config.ProfileName.PRODUCTION:
        log.info('External URL for task artifacts: %s/%s',
            config.get_config().artifacts_baseurl, arg_data['uuid'])
    log.info('Execution finished at: %s',
             datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC'))
    if not success:
        log.error('Some playbooks failed. Exiting with non-zero exit code.')
    sys.exit(0 if success else 1)
