# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Utility functions for dealing with Bodhi'''

from __future__ import absolute_import
import bodhi.client.bindings

from checkb import config
from checkb import exceptions as exc
from checkb.logger import log
from checkb import python_utils
from checkb.python_utils import basestring

from . import rpm_utils


class BodhiUtils(object):
    '''Helper Bodhi methods.

    :ivar bodhi.client.bindings.BodhiClient client: Bodhi client instance
    '''

    #: How many requests to make in a single call. The maximum page limit is
    #: 100, so it can't be above that. With high numbers, we increase the
    #: chance to receive a timeout.
    _MULTICALL_REQUEST_SIZE = 50

    def __init__(self, client=None):
        '''Create a new BodhiUtils instance.

        :param client: custom :class:`Bodhi2Client` instance. If ``None``, a
                       default Bodhi2Client instance is used.
        '''

        self.config = config.get_config()

        if not client:
            self.client = bodhi.client.bindings.BodhiClient(staging=self.config.bodhi_staging)
            log.debug('Created Bodhi client to: %s', self.client.base_url)
            # automatically retry failed requests (HTTP 5xx and similar)
            self.client.retries = 10
        else:
            self.client = client

    def get_update(self, updateid):
        '''Get the last Bodhi update for the specified update ID.

        :param str updateid: update ID, e.g. 'FEDORA-2015-13787'
        :return: Bodhi update object with that ID, or ``None`` when no such
                 update is found
        :rtype: :class:`munch.Munch`
        '''
        log.debug('Searching Bodhi updates for: %s', updateid)
        res = self.client.query(updateid=updateid)
        assert 0 <= len(res['updates']) <= 1

        if res['updates']:
            return res['updates'][0]
        else:
            return None

    def build2update(self, builds, strict=False):
        '''Find matching Bodhi updates for provided builds.

        :param builds: builds to search for in N(E)VR format (``foo-1.2-3.fc20``
                       or ``foo-4:1.2-3.fc20``)
        :type builds: iterable of str
        :param bool strict: if ``False``, incomplete Bodhi updates are allowed.
                            If ``True``, every Bodhi update will be compared
                            with the set of provided builds. If there is an
                            Bodhi update which contains builds not provided in
                            ``builds``, that update is marked as incomplete and
                            removed from the result - i.e. all builds from
                            ``builds`` that were part of this incomplete update
                            are placed in the second dictionary of the result
                            tuple.
        :return: a tuple of two dictionaries:

                 * The first dict provides mapping between ``builds`` and their
                   updates where no error occured.

                   ``{build (string): Bodhi update (Munch)}``
                 * The second dict provides mapping between ``builds`` and their
                   updates where some error occured. The value is ``None`` if
                   the matching Bodhi update could not be found (the only
                   possible cause of failure if ``strict=False``). Or the value
                   is a Bodhi update that was incomplete (happens only if
                   ``strict=True``).

                   ``{build (string): Bodhi update (Munch) or None}``
                 * The set of keys in both these dictionaries correspond exactly
                   to ``builds``. For every build provided in ``builds`` you'll
                   get an answer in either the first or the second dictionary,
                   and there will be no extra builds that you haven't specified.
        :raise CheckbValueError: if ``builds`` type is incorrect
        '''
        # validate input params
        if not python_utils.iterable(builds, basestring):
            raise exc.CheckbValueError(
                "Param 'builds' must be an iterable of strings, and yours was: %s" % type(builds))

        updates = []
        build2update = {}
        failures = {}
        # Bodhi works with NVR only, but we have to ensure we receive and return
        # even NEVR format. So we need to convert internally.
        builds_nvr = set([rpm_utils.rpmformat(build, 'nvr') for build in builds])
        builds_queue = list(builds_nvr)

        log.info('Querying Bodhi to map %d builds to their updates...', len(builds))

        # retrieve all update data
        while builds_queue:
            builds_chunk = builds_queue[:self._MULTICALL_REQUEST_SIZE]
            builds_chunk = ' '.join(builds_chunk)
            res = self.client.query(builds=builds_chunk)

            updates.extend(res['updates'])
            builds_queue = builds_queue[self._MULTICALL_REQUEST_SIZE:]

            # don't query for builds which were already found
            for update in res['updates']:
                for build in update['builds']:
                    if build['nvr'] in builds_queue:
                        builds_queue.remove(build['nvr'])

            log.info('Bodhi queries done: %d/%d', len(builds_nvr)-len(builds_queue),
                     len(builds_nvr))

        # separate builds into OK and failures
        for update in updates:
            # all builds listed in the update
            bodhi_builds = set([build['nvr'] for build in update['builds']])
            # builds *not* provided in @param builds but part of the update (NVRs)
            missing_builds = bodhi_builds.difference(builds_nvr)
            # builds provided in @param builds and part of the update
            matched_builds = [build for build in builds if
                              rpm_utils.rpmformat(build, 'nvr') in bodhi_builds]

            # reject incomplete updates when strict
            if missing_builds and strict:
                for build in matched_builds:
                    failures[build] = update
                continue

            # otherwise the update is complete or we don't care
            for build in matched_builds:
                build2update[build] = update

        # mark builds without any associated update as a failure
        for build in builds:
            if build not in build2update and build not in failures:
                failures[build] = None

        diff = set(builds).symmetric_difference(
            set(build2update.keys()).union(set(failures.keys())))
        assert not diff, "Returned NVRs different from input NVRs: %s" % diff

        return (build2update, failures)
