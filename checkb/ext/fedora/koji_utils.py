# -*- coding: utf-8 -*-
# Copyright 2009-2016, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

''' Utility methods related to Koji '''

from __future__ import absolute_import
import os
import sys
import koji
import hawkey

if (sys.version_info >= (3, 3)):
    import collections.abc as abc
else:
    import collections as abc

from checkb import file_utils
from checkb.logger import log
from checkb import exceptions as exc
from checkb import config
from checkb import arch_utils

from . import rpm_utils


class KojiClient(object):
    '''Helper Koji methods.

    :ivar koji.ClientSession session: Koji client session
    '''

    # example:
    # https://kojipkgs.fedoraproject.org/packages/kcalc/16.04.2/1.fc24/data/logs/x86_64/build.log
    build_log_url = \
        '{pkg_url}/{nevra.name}/{nevra.version}/{nevra.release}/data/logs/{nevra.arch}/build.log'

    def __init__(self, koji_session=None):
        '''Create a new KojiClient

        :param koji_session: an existing Koji session instance or ``None`` if
                             you want a new default session to be created
        :type koji_session: :class:`koji.ClientSession`
        '''
        opts = {
            # make koji retry even for non-logged-in connections.
            # retry behavior can be configured via 'max_retries' (default 30)
            # and 'retry_interval' (default 20) opts keys
            'anon_retry': True,
            # default Koji connection timeout is 12 hours, that's too high.
            # let's make it 5 minutes
            'timeout': 60 * 5}

        self.session = (koji_session or
                        koji.ClientSession(config.get_config().koji_url, opts=opts))

    def latest_by_tag(self, tags, pkgname):
        '''Get the latest Koji build for the given package name in the given tag(s).

        :param list tags: list of tags to be searched in
        :param str pkgname: name of the package
        :return: str containing NVR of the latest build, None if no build was found
        '''
        self.session.multicall = True
        for tag in tags:
            self.session.listTagged(tag, package=pkgname, latest=True)
        builds = self.session.multiCall()

        nvrs = []
        for build in builds:
            # see rpms_to_build for documentation on how multiCall works
            if isinstance(build, dict):
                raise exc.CheckbRemoteError('listTagged failed with: %d: %s' %
                                            (build["faultCode"], build["faultString"]))
            elif build[0]:
                assert len(build[0]) <= 1, 'More than one build returned with latest=True'
                nvrs.append(build[0][0]['nvr'])

        sorted_nvrs = sorted(nvrs, key=rpm_utils.sortkeyNEVR, reverse=True)
        if sorted_nvrs:
            return sorted_nvrs[0]

    def rpms_to_build(self, rpms):
        '''Get list of koji build objects for the rpms. Order of koji objects
        in this list is the same as order of the respective rpm objects.

        :param rpms: list of filenames as either ``/my/path/nvr.a.rpm`` or ``nvr.a.rpm``
        :type rpms: list of str
        :return: list of Koji buildinfo dictionaries (as returned e.g.
          from :meth:`koji.getBuild`) in the same respective order as in``rpms``
        :rtype: list
        :raise CheckbRemoteError: if rpm or it's related build is not found
        '''
        log.info('Querying Koji to map %d RPMs to their builds...', len(rpms))

        self.session.multicall = True
        for rpm in rpms:
            # extract filename from the (possible) path
            rpm = os.path.split(rpm)[-1]

            self.session.getRPM(rpm)

        # the list will contain one element for each method added to the
        # multicall, in the order it was added to the multicall
        rpminfos = self.session.multiCall()

        # because it is probable that several rpms will come from the same build
        # use set for builds
        builds = set()
        for i, rpminfo in enumerate(rpminfos):
            # according to documentation, multiCall() returns list, where
            # each element will be either a one-element list containing the
            # result of the method call, or a dict containing "faultCode" and
            # "faultString" keys, describing the error that occurred during the
            # method call.
            #
            # getRPM() returns None if there is no RPM with the given ID
            if isinstance(rpminfo, dict):
                raise exc.CheckbRemoteError('Problem with RPM %s: %d: %s' % (
                    rpms[i], rpminfo["faultCode"], rpminfo["faultString"]))
            elif rpminfo[0] is None:
                raise exc.CheckbRemoteError('RPM %s not found' % rpms[i])
            else:
                builds.add(rpminfo[0]['build_id'])

        builds = list(builds)  # so that we could use build order
        self.session.multicall = True
        for build in builds:
            self.session.getBuild(build)

        buildinfos = self.session.multiCall()

        for i, buildinfo in enumerate(buildinfos):
            # see ^
            if isinstance(buildinfo, dict):
                raise exc.CheckbRemoteError('Problem with build %s: %d: %s' %
                                            (builds[i], buildinfo["faultCode"],
                                                buildinfo["faultString"]))
            elif buildinfo[0] is None:
                raise exc.CheckbRemoteError(
                    'Build %s not found' % builds[i])

        build_to_buildinfo = dict(zip(builds, buildinfos))
        result = []
        for rpminfo in rpminfos:
            build_id = rpminfo[0]['build_id']
            result.append(build_to_buildinfo[build_id][0])

        return result

    @staticmethod
    def _compute_arches(arches, arch_exclude, src):
        '''
        From requested arches compute a final list of arches to be used by Koji calls.
        The input parameters have the same meaning as documented in :meth:`nvr_to_urls`.

        :return: a set of arches to be used
        :rtype: set of str
        '''
        arches = set(arches)
        arch_exclude = set(arch_exclude)
        # populate arches if 'all' requested
        if 'all' in arches:
            arches.discard('all')
            arches.update(config.get_config().supported_arches + ['noarch'])

        # add binary arches if base arches are specified
        for arch in arches.copy():
            if arch in arch_utils.Arches.base:
                arches.update(arch_utils.Arches.binary[arch])

        if src:
            arches.add('src')
        else:
            arch_exclude.add('src')

        # exclude unwanted arches
        arches.difference_update(arch_exclude)

        return arches

    def nvr_to_urls(self, nvr, arches=['all'], arch_exclude=[], debuginfo=False, src=True):
        '''Get list of URLs for RPMs corresponding to a build.

        :param str nvr: build NVR
        :param arches: restrict the arches of builds to provide URLs for. By default, all
            Checkb-supported architectures are considered. If you want to consider just some
            selected arches, provide their names in a list.

            .. note:: If you specify base arches (like ``i386``), all concrete binary arches for
              that base arch will be automatically added (e.g. ``i[3-6]86``), because Koji query
              requires concrete binary arches.
        :type arches: list of str
        :param arch_exclude: exclude some specific arches, even if they are specified in
            ``arches`` or they are implicit in the default ``'all'`` value
        :type arch_exclude: list of str
        :param bool debuginfo: whether to provide URLs for debuginfo RPM files
            or ignore them
        :param bool src: whether to include a URL for the source RPM
        :rtype: list of str
        :raise CheckbRemoteError: when the requested build doesn't exist
        '''
        arches = list(self._compute_arches(arches, arch_exclude, src))

        log.info('Querying Koji for a list of RPMs for: %s (arches %s)', nvr, sorted(arches))

        if not arches:
            log.debug('Nothing to query for, the combination of `arches`, `arch_exclude` and '
                      '`src` ended up an empty list.')
            return []

        # find the koji build
        info = self.session.getBuild(nvr)
        if info is None:
            raise exc.CheckbRemoteError("No such build found in Koji: %s" % nvr)

        # list its RPM files
        rpms = self.session.listRPMs(buildID=info['id'], arches=arches)
        if not debuginfo:
            rpms = [r for r in rpms if not is_debuginfo(r['name'])]

        if not rpms:
            log.debug('After excluding all unwanted arches and RPM files, there is no RPM file '
                      'left. Returning an empty list.')
            return []

        # create URLs
        baseurl = '/'.join((config.get_config().pkg_url, info['package_name'],
                            info['version'], info['release']))
        urls = ['%s/%s' % (baseurl, koji.pathinfo.rpm(r)) for r in rpms]

        return sorted(urls)

    def get_nvr_rpms(self, nvr, dest, arches=['all'], arch_exclude=[], debuginfo=False, src=False):
        '''Retrieve the RPMs associated with a build NVR into the specified
        directory.

        For parameters undocumented here, see :meth:`nvr_to_urls`.

        :param str nvr: build NVR
        :param str dest: location where to store the RPMs
        :return: list of local filenames of the grabbed RPMs (might be empty,
            according to your option choices and the particular NVR)
        :rtype: list of str
        :raise CheckbRemoteError: if the files can't be downloaded
        '''
        # always create dest dir, even if nothing gets downloaded
        file_utils.makedirs(dest)

        rpm_urls = self.nvr_to_urls(nvr, arches, arch_exclude, debuginfo, src)

        rpm_files = []
        log.info('Fetching %s RPMs for: %s (into %s)', len(rpm_urls), nvr, dest)

        # RPMs are safe to be cached, Koji guarantees they are immutable
        cachedir = None
        if config.get_config().download_cache_enabled:
            cachedir = config.get_config().cachedir

        for url in rpm_urls:
            rpm_file = file_utils.download(url, dest, cachedir=cachedir)
            rpm_files.append(rpm_file)

        return rpm_files

    def get_tagged_rpms(self, tag, dest, arches=['all'], arch_exclude=[], debuginfo=False,
                        src=False):
        '''Downloads all RPMs of all NVRs tagged by a specific Koji tag.

        Note: This works basically the same as :meth:`get_nvr_rpms`, it just
        downloads a lot of builds instead of a single one. For description of
        all shared parameters and return values, please see that method.

        :param str tag: Koji tag to be queried for available builds, e.g.
                        ``f20-updates-pending``
        '''
        # always create dest dir, even if nothing gets downloaded
        file_utils.makedirs(dest)

        log.info('Querying Koji for tag: %s', tag)
        tag_data = self.session.listTagged(tag)

        nvrs = sorted([x['nvr'] for x in tag_data])
        rpms = []
        log.info("Fetching %s builds for tag: %s", len(nvrs), tag)
        log.debug('Builds to be downloaded:\n  %s', '\n  '.join(nvrs))

        for nvr in nvrs:
            rpms.extend(self.get_nvr_rpms(nvr, dest, arches, arch_exclude, debuginfo, src))

        return rpms

    def get_build_log(self, nvr, dest, arches=['all'], arch_exclude=[]):
        '''Download a build.log file for NVR for each specified architecture and save it in
        ``dest`` as ``build.log.<arch>``.

        Note: Koji cleans up old log files regularly, i.e. they might not be available for a
        certain NVR. This method will not raise an error if that happens (the log file can't be
        downloaded). Instead, it will be simply missing in that directory and also marked in the
        returned object.

        For parameters undocumented here, see :meth:`nvr_to_urls`.

        :param str nvr: build NVR
        :param str dest: location where to store the log file
        :return: a dictionary of this structure:
            ::

                {'ok': ['/path/build.log.x86_64', '/path/build.log.i686'],
                 'error': ['armv7hl']
                }

            which describes which build logs were correctly downloaded and for which architectures
            we failed to download the logs.
        :rtype: dict
        :raise CheckbRemoteError: when the requested build doesn't exist or its info can't be
            retrieved
        '''
        log.info('Getting build logs for: %s', nvr)

        # there seem to be no logs in Koji for 'src'
        arches = self._compute_arches(arches, arch_exclude, src=False)
        if not arches:
            log.debug('Nothing to query for, the combination of `arches` and `arch_exclude` ended '
                      'up an empty list.')
            return {'ok': [], 'error': []}

        # list the RPMs for the koji build, so that we know which arches to download logs for
        try:
            build_rpms = self.session.listBuildRPMs(nvr)
        except koji.GenericError as e:
            log.exception("Could not query build %s: %s", nvr, e)
            raise exc.CheckbRemoteError(e)

        # download for each arch
        build_arches = set([rpm['arch'] for rpm in build_rpms])
        build_arches.intersection_update(arches)
        ok = []
        error = []
        for build_arch in build_arches:
            nevra = hawkey.split_nevra(nvr + '.' + build_arch)
            url = self.build_log_url.format(pkg_url=config.get_config().pkg_url, nevra=nevra)

            log.debug('Getting build.log for: %s %s', nvr, build_arch)
            try:
                log_file = file_utils.download(url=url, dirname=dest,
                                               filename='build.log.' + build_arch)
            except exc.CheckbRemoteError:
                error.append(build_arch)
                # file_utils.download() already logged important details, nothing more to do here
            else:
                ok.append(log_file)

        return {'ok': ok, 'error': error}


def getNEVR(build):
    '''Extract RPM version identifier in NEVR format from Koji build object

    :param dict build: Koji buildinfo dictionary (as returned e.g. from
                       :meth:`koji.getBuild`)
    :return: NEVR string; epoch is included when non-zero, otherwise omitted
    :raise CheckbValueError: if ``build`` is of incorrect type
    '''
    # validate input
    if (not isinstance(build, abc.Mapping) or 'nvr' not in build or
            'epoch' not in build):
        raise exc.CheckbValueError("Input argument doesn't look like "
                                      "a Koji build object: %s" % build)

    rpmver = hawkey.split_nevra(build['nvr'] + '.noarch')
    rpmver.epoch = build['epoch'] or 0
    nevr = '%s-%s' % (rpmver.name, rpmver.evr())
    # supress 0 epoch (evr() method always includes epoch, even if 0)
    nevr = rpm_utils.rpmformat(nevr, fmt='nevr')

    return nevr

def is_debuginfo(name):
    '''Determine whether RPM is a debuginfo file or not based on its name

    :param str name: RPM name (meaning a Name header value)
    :return: ``True`` or ``False``
    '''
    return (name.endswith('-debuginfo') or
        name.endswith('-debugsource') or
        ('-debuginfo-' in name))
