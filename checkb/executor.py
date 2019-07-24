# -*- coding: utf-8 -*-
# Copyright 2009-2017, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

from __future__ import absolute_import

import os
import os.path
import subprocess
import yaml
import fnmatch
import signal
import json
import tempfile
import requests
import re

from checkb import config
from checkb import image_utils
from checkb import os_utils
from checkb import file_utils
from checkb import arch_utils
from checkb.logger import log
from checkb import exceptions as exc
from checkb.directives import resultsdb_directive

try:
    from checkb.ext.disposable import vm
except ImportError as e:
    raise exc.CheckbImportError(e)


class Executor(object):
    '''Executor executes given task in the format of Ansible playbook. Before
    actual execution, executor decides where the playbook will be executed
    according to the config and command line options: locally, on existing
    machine or in a disposable client.

    :ivar dict arg_data: processed cli arguments with some extra runtime
                         variables
    :ivar task_vm: disposable client, instance of :class:`.TestCloudMachine`
    :ivar bool run_remotely: whether the task is run on a remote machine
    '''

    #: variables retrieved from tests.yml
    ACCEPTED_VARS = [
        # if you adjust this, also adjust writingtasks.rst
        'checkb_generic_task',
        'checkb_keepalive_minutes',
        'checkb_match_host_arch',
        'checkb_match_host_distro',
        'checkb_match_host_release',
    ]

    #: variables to be exposed in the task playbook
    FORWARDED_VARS = [
        # if you adjust this, also adjust writingtasks.rst
        'ansible_python_interpreter',  # internal, not documented
        'artifacts',
        'checkb_arch',
        'checkb_item_type',
        'checkb_item',
        'checkb_secrets_file',
        'checkb_supported_arches',
        'checkb_supported_binary_arches',
    ]

    def __init__(self, arg_data):
        self.arg_data = arg_data
        self.task_vm = None
        self.run_remotely = False
        self.ipaddr = self._get_client_ipaddr()

    def _spawn_vm(self, uuid, playbook_vars):
        '''Spawn a virtual machine using testcloud.

        :param str uuid: unicode string uuid for the task being executed
        :param dict playbook_vars: a vars dict created by
            :meth:`_create_playbook_vars`
        :returns: str ip address of spawned vm
        '''
        log.info('Spawning disposable client')

        env = image_utils.devise_environment(self.arg_data, playbook_vars)
        self.task_vm = vm.TestCloudMachine(uuid)

        retries = config.get_config().spawn_vm_retries

        while retries > 0:
            retries -= 1
            try:
                self.task_vm.prepare(**env)
                self.task_vm.wait_for_port(22)

                log.debug('Disposable client (%s %s) ready',
                    self.task_vm.instancename,
                    self.task_vm.ipaddr)

                return self.task_vm.ipaddr
            except vm.TestcloudInstanceError as e:
                if retries <= 0:
                    raise exc.CheckbMinionError('Disposable client failed '
                        'to boot: %s', e)
                else:
                    log.warning('Disposable client failed to boot, retrying: '
                        '%s', e)
                    self.task_vm.teardown()

    def _get_client_ipaddr(self):
        '''Get an IP address of the machine the task is going to be executed
        on.

        :returns: str ip address of the machine or None if the machine is yet
        to be created
        '''
        # when running remotely, run directly over ssh, instead of using
        # libvirt
        persistent = False

        runtask_mode = config.get_config().runtask_mode
        if runtask_mode == config.RuntaskModeName.LOCAL:
            self.run_remotely = False
        elif runtask_mode == config.RuntaskModeName.LIBVIRT:
            self.run_remotely = True
        else:
            assert False, 'This should never occur'

        if self.arg_data['local']:
            log.debug("Forcing local execution (option --local)")
            self.run_remotely = False

        elif self.arg_data['libvirt']:
            log.debug("Forcing remote execution (option --libvirt)")
            self.run_remotely = True
            persistent = False

        elif self.arg_data['ssh']:
            log.debug('Forcing remote execution (option --ssh)')
            self.run_remotely = True
            persistent = True

        log.debug('Execution mode: %s', 'remote' if self.run_remotely
            else 'local')

        ipaddr = '127.0.0.1'
        if self.run_remotely:
            ipaddr = self.arg_data['machine'] if persistent else None

        return ipaddr

    @staticmethod
    def _check_playbook_syntax(playbook):
        '''Run ansible-playbook --syntax-check on a playbook

        :param str playbook: path to an ansible playbook
        :raise CheckbPlaybookError: when the playbook is not syntactically
            correct
        '''
        try:
            subprocess.check_call(['ansible-playbook', '--syntax-check',
                playbook])
            log.debug('Playbook is syntactically correct: %s', playbook)
        except subprocess.CalledProcessError as e:
            log.error('Syntax check failed for playbook %s: %s', playbook,
                      e)
            raise exc.CheckbPlaybookError(e)

    def _load_playbook_vars(self, test_playbook):
        '''Load accepted playbook vars from a playbook file and return it
        as a dict.

        :param str test_playbook: name of the playbook, relative to the task
            directory
        :return: a dict with keyvals from the playbook which are allowed to be
            loaded (see :attr:`ACCEPTED_VARS`).
        '''
        vars_ = {}
        with open(os.path.join(self.arg_data['taskdir'], test_playbook), 'r') \
        as playbook_file:
            playbook_yaml = yaml.safe_load(playbook_file.read())
            # we only consider variables in the first play
            playbook_vars = playbook_yaml[0].get('vars', {})
        for var, val in playbook_vars.items():
            if var in self.ACCEPTED_VARS:
                vars_[var] = val
        return vars_

    def _get_vault_secrets(self, taskdir):
        '''Load secrets from the Vault server and store them in a file

        :param str taskdir: path to the directory with test suite (on overlord)
        :return: a filename with decrypted secrets
        '''
        cfg = config.get_config()
        secrets = {}
        if cfg.vault_enabled:
            task_repo_url = resultsdb_directive.git_origin_url(taskdir)
            if task_repo_url:
                try:
                    session = file_utils._get_session()
                    r = session.get(
                            "%s/buckets" % cfg.vault_server,
                            auth=(cfg.vault_username, cfg.vault_password),
                        )
                except requests.exceptions.RequestException as e:
                    log.error("Connection to Vault server failed. %s", e)
                    r = None

                if r and r.ok:
                    data = r.json()['data']
                    valid_buckets = []
                    re_enabler = re.compile(r'checkb_enable\((.*?)\)')
                    for b in data:
                        desc = b['description']
                        if not desc:
                            continue
                        enabled_for = ', '.join(re_enabler.findall(desc))
                        if not task_repo_url in enabled_for:
                            continue
                        valid_buckets.append(b)
                    for b in valid_buckets:
                        secrets[b['uuid']] = b['secrets']
                elif r and not r.ok:
                    log.error("Could not get data from vault. %r, %r", r.status_code, r.reason)

        if config.get_config().profile == config.ProfileName.TESTING:
            return secrets

        fd, fname = tempfile.mkstemp(prefix='checkb_secrets')
        os.close(fd)
        with open(fname, 'w') as fd:
            fd.write(json.dumps(secrets, indent=2, sort_keys=True))
        return fname

    def _create_playbook_vars(self, test_playbook):
        '''Create and return dictionary containing all variables to be used
        with our ansible playbook.

        :param str test_playbook: name of the playbook, relative to the task
            directory

        :return: A dictionary containing these keys:

            artifacts_root
                path to the root artifacts directory (on overlord and minion)
            artifacts
                path to the playbook-specific artifacts directory (on overlord
                and minion)
            become_root
                whether to run playbooks as root
            client_taskdir
                path to directory with test suite (on minion)
            heartbeat_file
                heartbeat will appear in this file
            heartbeat_interval
                add line to heartbeat_file every x seconds (2 minutes)
            local
                running on local machine (overlord), no remote connection
            minion_repos
                a list of repos (strings) to install on the minion
            minion_repos_ignore_errors
                whether to ignore errors when adding minion repos
            taskdir
                path to directory with test suite (on overlord)
            checkb_arch
                architecture of checkb_item to be tested
            checkb_generic_task
                whether this is a Checkb task, or a random ansible playbook
            checkb_item_type
                item under test
            checkb_item
                item type under test
            checkb_keepalive_minutes
                how long should heartbeat process run (0 to disable)
            checkb_match_host_arch
                whether VM guest arch has to match checkb_arch
            checkb_match_host_distro
                whether VM guest distro has to match checkb_item
            checkb_match_host_release
                whether VM guest release has to match checkb_item
            checkb_secrets_file
                path to the file with secrets appropriate for the task
            checkb_supported_arches
                list of base architectures supported by Checkb (e.g.
                'armhfp')
            checkb_supported_binary_arches
                list of base+binary architectures supported by Checkb (e.g.
                'armhfp, armv7hl')
            test_playbook
                path to playbook to execute inside client_taskdir (usually
                tests.yml)
            varsfile
                name of the ansible vars file inside ``artifacts/checkb/``
                to forward to task
        '''

        vars_ = {}
        cfg = config.get_config()

        # default values
        vars_['become_root'] = True
        vars_['checkb_generic_task'] = False
        vars_['heartbeat_interval'] = 120
        vars_['checkb_keepalive_minutes'] = 0
        vars_['checkb_match_host_arch'] = False
        vars_['checkb_match_host_distro'] = False
        vars_['checkb_match_host_release'] = False
        vars_['varsfile'] = 'task_vars.json'
        # Ansible on F30 defaults to Python2, which fails with dnf module
        # due to missing python2-dnf package
        vars_['ansible_python_interpreter'] = '/usr/bin/python3'

        # load all allowed vars from tests.yml
        loaded_vars = self._load_playbook_vars(test_playbook)
        vars_.update(loaded_vars)

        # compute vars
        vars_['artifacts'] = os.path.join(self.arg_data['artifactsdir'],
            test_playbook)
        vars_['artifacts_root'] = self.arg_data['artifactsdir']
        vars_['client_taskdir'] = cfg.client_taskdir
        vars_['heartbeat_file'] = os.path.join(vars_['artifacts_root'],
            'checkb', 'heartbeat.log')
        vars_['local'] = not self.run_remotely
        vars_['minion_repos'] = cfg.minion_repos
        vars_['minion_repos_ignore_errors'] = cfg.minion_repos_ignore_errors
        vars_['taskdir'] = self.arg_data['taskdir']
        vars_['checkb_arch'] = self.arg_data['arch']
        vars_['checkb_item'] = self.arg_data['item']
        vars_['checkb_item_type'] = self.arg_data['type']
        vars_['checkb_secrets_file'] = self._get_vault_secrets(taskdir=vars_['taskdir'])
        vars_['checkb_supported_arches'] = cfg.supported_arches
        vars_['checkb_supported_binary_arches'] = [binarch for arch in
            cfg.supported_arches for binarch in arch_utils.Arches.binary[arch]]
        vars_['test_playbook'] = test_playbook

        return vars_

    def _dump_playbook_vars(self, playbook_vars):
        '''Save playbook variables into json files, so that they can serve
        later for forwarding vars to task playbooks and for debugging.

        :param dict playbook_vars: vars dict created by
            :meth:`_create_playbook_vars`
        :return: tuple of ``(varsfile, allvarsfile)``, where ``varsfile`` is
            a path to json file with variables to be forwarded to task
            playbooks, and ``allvarsfile`` is a path to json file with whole
            ``playbook_vars`` content (useful for debugging)
        '''

        # save forwarded variables, so that task playbook can load them
        fwdvars = {}
        for fwdvar in self.FORWARDED_VARS:
            fwdvars[fwdvar] = playbook_vars[fwdvar]
        file_utils.makedirs(os.path.join(playbook_vars['artifacts'],
            'checkb'))
        varsfile = os.path.join(playbook_vars['artifacts'], 'checkb',
                playbook_vars['varsfile'])
        with open(varsfile, 'w') as vf:
            vars_str = json.dumps(fwdvars, indent=2, sort_keys=True)
            vf.write(vars_str)
            log.debug('Saved task vars file %s with contents:\n%s',
                      varsfile, vars_str)

        # save also all runner playbook variables, for debugging
        allvarsfile = os.path.join(playbook_vars['artifacts'], 'checkb',
            'internal_vars.json')
        with open(allvarsfile, 'w') as vf:
            vars_str = json.dumps(playbook_vars, indent=2, sort_keys=True)
            vf.write(vars_str)
            log.debug('Saved internal ansible vars file %s with contents:\n%s',
                      allvarsfile, vars_str)

        return (varsfile, allvarsfile)

    def _run_playbook(self, test_playbook, ipaddr, playbook_vars):
        '''Run the ansible-playbook command to execute given playbook
        containing the task.

        :param str test_playbook: name of the playbook, relative to the task
            directory
        :param str ipaddr: IP address of the machine the task will be run on
        :param dict playbook_vars: vars dict created by
            :meth:`_create_playbook_vars`
        :return: stream output of the ansible-playbook command (stdout and
            stderr merged together)
        :rtype: str
        :raise CheckbPlaybookError: when the playbook is not syntactically
            correct
        '''
        ansible_dir = os.path.join(config.get_config()._data_dir, 'ansible')

        # dump variables for future use
        varsfile, allvarsfile = self._dump_playbook_vars(playbook_vars)

        # figure out the ansible-playbook command
        cmd = [
            'ansible-playbook', 'runner.yml',
            '--inventory=%s,' % ipaddr,  # the ending comma is important
            '--extra-vars=@%s' % allvarsfile,
        ]

        # for local execution, run as root unless instructed otherwise
        if not self.run_remotely and playbook_vars['become_root']:
            cmd.append('--become')

        if self.run_remotely:
            if self.arg_data['ssh_privkey']:
                cmd.append('--private-key=%s' % self.arg_data['ssh_privkey'])
        else:
            cmd.append('--connection=local')

        if self.arg_data['debug']:
            cmd.append('-vv')

        log.debug('Running ansible playbook %s', ' '.join(cmd))
        try:
            # during playbook execution, handle system signals asking us to
            # quit
            signal.signal(signal.SIGINT, self._interrupt_handler)
            signal.signal(signal.SIGTERM, self._interrupt_handler)

            output, _ = os_utils.popen_rt(cmd, cwd=ansible_dir)
            return output
        except subprocess.CalledProcessError as e:
            log.error('ansible-playbook ended with %d return code',
                      e.returncode)
            log.debug(e.output)
            raise exc.CheckbError(e)
        except exc.CheckbInterruptError as e:
            log.error('System interrupt %s detected. Pulling logs and '
                      'stopping execution.', e)
            cmd_failsafe = cmd + ['--tags', 'failsafe']
            try:
                os_utils.popen_rt(cmd_failsafe, cwd=ansible_dir)
            except (subprocess.CalledProcessError,
                    exc.CheckbInterruptError) as e2:
                log.error('Error during failsafe pulling logs, ignoring and '
                    'raising the original error. The current error is: %s:%s',
                    e2.__class__.__name__, e2)
            raise e
        finally:
            # reset signal handling to default behavior
            signal.signal(signal.SIGINT, signal.SIG_DFL)
            signal.signal(signal.SIGTERM, signal.SIG_DFL)

    def _interrupt_handler(self, signum, frame):
        '''Catch system signals (like SIGINT, SIGTERM) and raise them
        as a TasktoronInterruptError'''
        signals_to_names = dict((getattr(signal, n), n) for n in dir(signal)
            if n.startswith('SIG') and '_' not in n )
        signame = signals_to_names.get(signum, 'UNKNOWN')

        log.warning('Received system signal %d (%s). Raising exception.',
                    signum, signame)
        raise exc.CheckbInterruptError(signum, signame)

    def _report_results(self, test_playbook):
        '''Report results from playbook's ``results.yml`` (stored in
        artifactsdir) into ResultsDB.

        :param str test_playbook: base name of the playbook file
        :raise CheckbDirectiveError: when there's a problem processing
            ``results.yml`` file
        '''
        results_file = os.path.join(self.arg_data['artifactsdir'],
            test_playbook, 'checkb', 'results.yml')
        log.info('Reporting results from: %s', results_file)

        if not os.path.exists(results_file):
            raise exc.CheckbDirectiveError("Results file doesn't exist, "
                'assuming the task crashed. If you wish to report no results, '
                'the results file still needs to exist - consult '
                'documentation. Expected results file location: %s' %
                                           results_file)

        rdb = resultsdb_directive.ResultsdbDirective()
        rdb.process(params={"file": results_file}, arg_data=self.arg_data)

        # create file indicating that results were reported to resultsdb
        reported_file = os.path.join(self.arg_data['artifactsdir'],
            test_playbook, 'checkb', 'results.yml.reported_ok')
        open(reported_file, 'a').close()

    def execute(self):
        '''Execute all the tasks in the taskdir

        :return: ``True`` if execution finished successfully for all playbooks
            present. ``False`` if some of them crashed, haven't produced any
            results or the execution was interrupted (e.g. a system signal).
        :rtype: bool
        '''
        test_playbooks = fnmatch.filter(os.listdir(self.arg_data['taskdir']),
                                                   'tests*.yml')
        if not test_playbooks:
            raise exc.CheckbError('No tests*.yml found in dir %s' %
                                  self.arg_data['taskdir'])

        failed = []
        for test_playbook in test_playbooks:
            playbook_vars = None
            try:
                # syntax check
                self._check_playbook_syntax(os.path.join(
                    self.arg_data['taskdir'], test_playbook))

                # compute variables
                playbook_vars = self._create_playbook_vars(test_playbook)

                if not playbook_vars['checkb_generic_task']:
                    raise exc.CheckbPlaybookError('This playbook is not '
                        'marked as a Checkb generic task. See '
                        'documentation how to write a task.')

                # spawn VM if needed
                ipaddr = self.ipaddr
                if ipaddr is None:
                    ipaddr = self._spawn_vm(self.arg_data['uuid'],
                        playbook_vars)

                # execute
                log.info('Running playbook %s on machine: %s', test_playbook,
                    ipaddr)
                self._run_playbook(test_playbook, ipaddr, playbook_vars)

                # report results
                self._report_results(test_playbook)
            except exc.CheckbInterruptError as e:
                log.error('Caught system interrupt during execution of '
                    'playbook %s: %s. Not executing any other playbooks.',
                    test_playbook, e)
                failed.append(test_playbook)
                break
            except exc.CheckbError as e:
                log.error('Error during execution of playbook %s: %s',
                    test_playbook, e)
                failed.append(test_playbook)
            finally:
                try:
                    if playbook_vars and config.get_config().profile != config.ProfileName.TESTING:
                        os.remove(playbook_vars['checkb_secrets_file'])
                except OSError as e:
                    log.warning("Could not delete the secrets file at %r. %s",
                                playbook_vars['checkb_secrets_file'], e)
                if self.task_vm is not None:
                    if self.arg_data['no_destroy']:
                        log.info('Not destroying disposable client as '
                                 'requested, access it at: %s . Skipping any '
                                 'other playbooks.', ipaddr)
                        break
                    else:
                        self.task_vm.teardown()
                log.info('Playbook execution finished: %s', test_playbook)

        if failed:
            log.error('Some playbooks failed during execution: %s',
                ', '.join(failed))
        else:
            log.info('All playbooks finished successfully')

        return not failed
