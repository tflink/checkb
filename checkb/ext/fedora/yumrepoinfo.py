# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''A wrapper object for yumrepoinfo.conf to access its information easily'''

from __future__ import absolute_import
import os
import socket

try:
    # Python 3
    import configparser
    PARSER_CLASS = configparser.ConfigParser
    from urllib.request import urlopen
    from urllib.error import URLError
except ImportError:
    # Python 2
    import ConfigParser as configparser
    PARSER_CLASS = configparser.SafeConfigParser
    from urllib2 import urlopen, URLError

from checkb import config
from checkb.logger import log
from checkb import arch_utils
from checkb import exceptions as exc


# a singleton instance of YumRepoInfo (a dict with arches as keys)
_yumrepoinfo = {}


def get_yumrepoinfo(arch=None, filelist=None):
    '''Get YumRepoInfo instance. This method is implemented using the singleton
    pattern - you will always receive the same instance, which will get
    auto-initialized on the first method call.

    :param str arch: architecture to return the YumRepoInfo for. It's always
                     converted to basearch. If ``None``, then local machine arch
                     is used.
    :param filelist: list of config files to read information from. The
                     first available config file is used. If ``None``, then
                     the default list of locations is used.
    :return: shared :class:`YumRepoInfo` instance
    :raise CheckbConfigError: if file config parsing and handling failed
    '''
    # converts to basearch, returns local arch for None
    arch = arch_utils.basearch(arch)

    if not arch in _yumrepoinfo:
        _yumrepoinfo[arch] = YumRepoInfo(arch, filelist)
    return _yumrepoinfo[arch]


class YumRepoInfo(object):
    '''This class is a wrapper for easily accessing repoinfo.conf file.'''

    def __init__(self, arch=None, filelist=None, resolve_baseurl=True,
                 resolve_retry=3):
        '''
        :param str arch: architecture for which to adjust repo URLs. By default
                    it refers to the architecture of the current machine. It's
                    always converted to basearch.
        :param filelist: list of config files to read information from. The
                        first available config file is used. If ``None``, then
                        the default list of locations is used.
        :type filelist: iterable of str
        :param bool resolve_baseurl: if baseurl is a known redirect, resolve
            it for each section during initialization. If this is ``False``,
            you must call :meth:`_switch_to_mirror` manually.
        :param int resolve_retry: how many tries to retry resolving the URL
            for each section in case the network request fails
        :raise CheckbConfigError: if no YUM repositories data is found (empty
                                     or non-existent config file). It's not
                                     raised if you specifically request no data
                                     to load (``filelist=[]``).
        :raise CheckbRemoteError: if url resolving fails
        '''
        if config.get_config().profile == config.ProfileName.TESTING:
            resolve_baseurl = False

        self.arch = arch_utils.basearch(arch)
        self.filelist = (filelist if filelist is not None else
            [os.path.join(confdir, 'yumrepoinfo.conf')
             for confdir in config.CONF_DIRS])
        self.resolve_retry = resolve_retry
        self.parser = PARSER_CLASS(defaults=
            {'arch': self.arch})

        if not self.filelist:
            # no data should be loaded
            return

        self._read()

        if not self.repos():
            msg = ("No YUM repo definitions found in the following locations: "
                   "%s" % self.filelist)
            log.critical(msg)
            raise exc.CheckbConfigError(msg)

        self._adjust_baseurl()

        # download.fp.o is a known redirect
        if resolve_baseurl and ('download.fedoraproject.org' in
            self.parser.get('DEFAULT', 'baseurl')):
            self._switch_to_mirror()

    def repos(self):
        '''Get the list of all known repository names.

        :rtype: list of str
        '''
        return self.parser.sections()


    def releases(self):
        '''Get the list of stable (supported) Fedora releases.

        :rtype: list of str
        '''
        return [r for r in self.repos() if self.get(r, 'release_status').lower()
                == "stable"]


    def branched(self):
        '''Get branched Fedora release (or None if it doesn't exist).

        :rtype: str or None
        '''
        for r in self.repos():
            if self.get(r, 'release_status').lower() == 'branched':
                return r
        return None


    def arches(self, reponame):
        '''Get a list of all supported (primary and alternate) architectures for a repo

        :param str reponame: repository name
        '''
        return (self._getlist(reponame, 'primary_arches') +
                self._getlist(reponame, 'alternate_arches'))


    def get(self, reponame, key):
        '''Get a specific key value from a repo

        :param str reponame: repository name
        :param str key: name of the key you want to retrieve from a repository
                        (section)
        :raise CheckbConfigError: if the key can't be retrieved (e.g. wrong
                                     key or repo name)
        '''
        try:
            return self.parser.get(reponame, key)
        except configparser.Error as e:
            raise exc.CheckbConfigError("Can't retrieve key '%s' from repo "
                "'%s': %s" % (key, reponame, e))


    def repo(self, reponame):
        '''Given a repo name, return the yumrepoinfo dict with keys:
        ``arches``, ``parents``, ``tag``, ``url``, ``path`` and ``name``

        :param str reponame: repository name
        :rtype: dict
        '''
        repo = {'arches': self.arches(reponame),
                'parent': self.get(reponame, 'parent'),
                'tag': self.get(reponame,'tag'),
                'url': self.get(reponame,'url'),
                'path': self.get(reponame,'path'),
                'name': reponame,
        }
        return repo


    def repo_by_tag(self, tag):
        '''Given a Koji tag, return the corresponding repo dict.

        :param str tag: a koji tag, e.g. ``f20-updates``. Note: ``rawhide`` is
                        not used as a Koji tag, use number identifier instead or
                        use :meth:`repo('rawhide')['tag'] <repo>` to discover it
                        first.
        :return: repo dict as from :meth:`repo`, or ``None`` if no such Koji tag
                 is found
        '''
        # we don't have repo definition for -candidate tags,
        # let's go up in the hierarchy (stripping '-candidate')
        if tag.endswith('-candidate'):
            tag = tag[:-len('-candidate')]
        for r in self.repos():
            if self.get(r,'tag') == tag:
                return self.repo(r)


    def top_parent(self, reponame):
        '''Go through the repo hiearchy and find the top parent for a repo

        :param str reponame: repository name
        :return: the top parent reponame. If ``reponame`` doesn't have any
                 parent, its name is returned (it's its own top parent)
        :rtype: str
        :raise CheckbConfigError: if infinite parent loop detected
        '''
        parents = []
        repo = reponame

        while True:
            parent = self.get(repo, 'parent')

            if not parent:
                # we've found the top parent
                return repo

            # detect infinite parent loops
            if parent in parents:
                raise exc.CheckbConfigError('Infinite parent loop detected '
                    'in yumrepoinfo: %s' % parents)

            parents.append(parent)
            repo = parent


    def release_status(self, reponame):
        '''Return release status of specified repo. For non-top-parent repos,
        return release_status of top parent repo.

        :param str reponame: repository name
        :return: release status of specified repo, lowercased. One of:
            `rawhide`, `branched`, `stable`, `obsolete`.
        :rtype: str
        '''
        return self.get(self.top_parent(reponame), 'release_status').lower()


    def _read(self):
        '''Read first available config file from the list of provided config
        files.'''
        log.debug('Looking for yumrepoinfo config files in: %s', self.filelist)

        for cfg in self.filelist:
            if self.parser.read(cfg):
                log.debug('Successfully loaded yumrepoinfo config file: %s',
                          cfg)
                break
            else:
                log.debug('Failed to load yumrepoinfo config file: %s', cfg)


    def _getlist(self, reponame, key):
        '''Transform a list of comma separated values into a Python list.
        Returns empty list for a non-existent key.

        :param str reponame: repository name
        :param str key: name of the key you want to retrieve from a repository
                        (section), and then convert it to a list
        :rtype: list of str
        '''
        itemlist = self.get(reponame, key)
        if not itemlist:
            return []
        else:
            return [t.strip() for t in itemlist.split(',')]

    def _adjust_baseurl(self):
        '''We need to adjust baseurl if the requested arch is an alternate one
        for that repo.

        This is supposed to be called only once during initialization.
        '''
        for section in self.parser.sections():
            if (self.parser.has_option(section, 'alternate_arches') and
                self.arch in self._getlist(section, 'alternate_arches')):
                self.parser.set(section, 'baseurl',
                    self.get(section, 'baseurl_altarch'))

    def _switch_to_mirror(self):
        '''If the baseurl is a round-robin redirect (as in case of
        ``download.fedoraproject.org``), resolve the ``url`` in each section
        and save it back. This avoids issues with multiple network requests
        being directed each to a different mirror (possibly with different
        contents).

        This is supposed to be called only once during initialization.
        '''
        log.info('Resolving URLs in yumrepoinfo config, because the baseurl '
            'is a well-known redirect. Provide a custom mirror to skip this '
            'in the future.')

        for section in self.parser.sections():
            if section == 'DEFAULT':
                continue

            retries = 0
            url = self.parser.get(section, 'url')
            newurl = None

            while retries <= self.resolve_retry:
                try:
                    log.debug('Resolving url: %s', url)
                    response = urlopen(url, timeout=20)
                    newurl = response.geturl()
                    break
                except (URLError, socket.error) as e:
                    retries += 1
                    log.warning('Received %s when resolving %s . %s', e, url,
                        'Trying again...' if retries <= self.resolve_retry else
                        'Giving up.')
                    if retries > self.resolve_retry:
                        raise exc.CheckbRemoteError(
                            'Failed to resolve %s : %s' % (url, e))

            self.parser.set(section, 'url', newurl)
            log.debug('Set %s section to use url: %s', section, newurl)
