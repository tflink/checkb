# -*- coding: utf-8 -*-
# Copyright 2009-2016, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''This includes the default values for Checkb configuration. This is
automatically loaded by config.py and then overridden by values from config
files available in system-wide location.'''

from __future__ import absolute_import
import pprint


class ProfileName(object):
    '''Enum of available profile names. These can be specified in the config
    file or as the environment variable.'''

    DEVELOPMENT = 'development'  #:
    PRODUCTION = 'production'    #:
    TESTING = 'testing'          #:


class RuntaskModeName(object):
    '''Enum of available runtask mode names. These can be specified in
    the config file.'''

    LIBVIRT = 'libvirt'  #:
    LOCAL = 'local'      #:


class Config(object):
    '''Global configuration for Checkb (development profile).

       The documentation for individual options is available in the config
       files (unless they're not present in the config files, then they're
       documented here).

       Implementation notes:

       * If you want to add a new option, put it here and optionally into the
         config file as well.
       * If you modify a default value for some option, don't forget to modify
         it in both places - here and in the config file (if present).
       * Don't assign ``None`` as a default value. We need to know a value type
         in order to check for correct type of user-provided values.
    '''

    '''Filename of the loaded config file. To be set after an external
       config file is loaded from the disk and its values merged with the
       default values. (If no config file is found, this is going to
       stay empty). *Do not* set this value manually in a config file
       itself - it is for internal use only.'''
    _config_filename = ''                                                   #:
    '''Path to the library data files. Always converted to an absolute path
    after initialization. *Do not* set this value manually, it's for internal
    use only.'''
    _data_dir = '../data'                                                   #:

    profile = ProfileName.DEVELOPMENT                                       #:

    runtask_mode = RuntaskModeName.LOCAL                                    #:
    supported_arches = ['x86_64', 'armhfp']                                 #:

    report_to_resultsdb = False                                             #:

    buildbot_task_step = 'runtask'                                          #:

    koji_url = 'https://koji.fedoraproject.org/kojihub'                     #:
    pkg_url = 'https://kojipkgs.fedoraproject.org/packages'                 #:
    bodhi_staging = False                                                   #:
    execdb_server = 'http://localhost:5003'                                 #:
    resultsdb_server = 'http://localhost:5001/api/v2.0'                     #:
    resultsdb_frontend = 'http://localhost:5002'                            #:
    checkb_master = 'http://localhost/taskmaster'                        #:
    artifacts_baseurl = 'http://localhost/artifacts'                        #:
    download_cache_enabled = True                                           #:
    vault_enabled = False                                                   #:
    vault_server = 'http://localhost:4999/api/v1'                           #:
    vault_username = 'checkb'                                            #:
    vault_password = 'checkb'                                            #:

    tmpdir = '/var/tmp/checkb'                                           #:
    logdir = '/var/log/checkb'                                           #:
    client_taskdir = '/var/tmp/checkb/taskdir'                           #:
    artifactsdir = '/var/lib/checkb/artifacts'                           #:
    cachedir = '/var/cache/checkb'                                       #:
    imagesdir = '/var/lib/checkb/images'                                 #:
    imageurl = 'http://download.fedoraproject.org/pub/fedora/linux/'\
               'releases/27/CloudImages/x86_64/images/'\
               'Fedora-Cloud-Base-27-1.6.x86_64.qcow2'                      #:
    force_imageurl = True                                                   #:
    default_disposable_distro = 'fedora'                                    #:
    default_disposable_release = '28'                                       #:
    default_disposable_flavor = 'checkb_cloud'                           #:
    default_disposable_arch = 'x86_64'                                      #:

    spawn_vm_retries = 3                                                    #:

    minion_repos = []                                                       #:
    minion_repos_ignore_errors = False                                      #:

    log_level_stream = 'INFO'                                               #:
    log_level_file = 'DEBUG'                                                #:

    log_file_enabled = False                                                #:

    ssh_privkey = ''                                                        #:

    def __str__(self):
        ''' Make this object more readable when printing '''
        return '<%s: %s>' % (self.__class__.__name__,
                             pprint.pformat(vars(self)))


class ProductionConfig(Config):
    '''Configuration for production profile. Inherits values from
    :class:`Config` and overrides some. Read Config documentation.'''

    profile = ProfileName.PRODUCTION                                        #:

    runtask_mode = RuntaskModeName.LIBVIRT                                  #:

    report_to_resultsdb = True                                              #:

    download_cache_enabled = False                                          #:

    log_level_stream = 'INFO'                                               #:
    log_level_file = 'DEBUG'                                                #:

    log_file_enabled = True                                                 #:


class TestingConfig(Config):
    '''Configuration for testing suite profile. Inherits values from
    :class:`Config` and overrides some. Read Config documentation.'''

    profile = ProfileName.TESTING                                           #:

    tmpdir = '/var/tmp/checkb-test/tmp'                                  #:
    logdir = '/var/tmp/checkb-test/log'                                  #:
    artifactsdir = '/var/tmp/checkb-test/artifacts'                      #:
    cachedir = '/var/tmp/checkb-test/cache'                              #:

    log_level_stream = 'DEBUG'                                              #:
    log_level_file = 'DEBUG'                                                #:
