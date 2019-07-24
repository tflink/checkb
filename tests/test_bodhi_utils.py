# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

'''Unit tests for checkb/bodhi_utils.py'''

import pytest
import mock
from munch import Munch

import bodhi.client.bindings

from checkb.ext.fedora import bodhi_utils
from checkb import exceptions as exc
from checkb import config


class TestBodhiUtils():
    '''Test generic functionality'''

    def test_staging_or_production(self, monkeypatch):
        '''Client should be correctly created when requested staging in config or not'''
        monkeypatch.setattr(config, '_config', None)
        conf = config.get_config()
        assert conf.bodhi_staging is False
        bu = bodhi_utils.BodhiUtils()
        prod_url = bu.client.base_url

        conf.bodhi_staging = True
        bu_stg = bodhi_utils.BodhiUtils()
        stg_url = bu_stg.client.base_url

        assert prod_url != stg_url
        assert prod_url == bodhi.client.bindings.BASE_URL
        assert stg_url == bodhi.client.bindings.STG_BASE_URL


class TestGetUpdate():
    '''Test get_update()'''

    def setup_method(self, method):
        '''Run this before every test invocation'''
        self.ref_update_id = 'FEDORA-1234-56789'
        self.ref_update = {'title': 'Random update',
                           'builds': [{'nvr': 'foo-1.2-3.fc99',
                                       'package': {}
                                       }],
                           'other_keys': {},
                           }

    def test_query_existing_update(self):
        '''Test query for existing update'''
        ref_query_answer = {'updates': [self.ref_update]}
        stub_bodhi = mock.Mock(**{'query.return_value': ref_query_answer})
        bodhi = bodhi_utils.BodhiUtils(client=stub_bodhi)
        update = bodhi.get_update(self.ref_update_id)

        assert update == self.ref_update

    def test_query_non_existing_update(self, monkeypatch):
        '''Test query for non-existing update'''
        ref_query_answer = {'updates': []}
        stub_bodhi = mock.Mock(**{'query.return_value': ref_query_answer})
        bodhi = bodhi_utils.BodhiUtils(client=stub_bodhi)
        update = bodhi.get_update(self.ref_update_id)

        assert update is None


@pytest.mark.usefixtures('setup')
class TestBuild2Update():
    '''Test build2update()'''

    # fake requests and responses for query_update()
    multi1 = Munch(builds=[Munch(nvr=u'multi1-a-1.0-1.fc20'),
                           Munch(nvr=u'multi1-b-2.0-2.fc20')])
    multi2 = Munch(builds=[Munch(nvr=u'multi2-a-1.0-1.fc20'),
                           Munch(nvr=u'multi2-b-2.0-2.fc20')])
    requests = {
        'foo-ok-1.2-3.fc20': Munch(builds=[Munch(nvr=u'foo-ok-1.2-3.fc20')]),
        'bar-ok-1.8.0-4.fc20': Munch(builds=[Munch(nvr=u'bar-ok-1.8.0-4.fc20')]),
        'multi1-a-1.0-1.fc20': multi1,
        'multi1-b-2.0-2.fc20': multi1,
        'multi2-a-1.0-1.fc20': multi2,
        'multi2-b-2.0-2.fc20': multi2,
    }

    def mock_query(self, builds):
        '''Mock bodhi.client.query()'''
        builds = builds.split()
        updates = []
        for build in builds:
            if build in self.requests:
                if self.requests[build] not in updates:
                    updates.append(self.requests[build])
        return Munch(updates=updates)

    @pytest.fixture
    def setup(self, monkeypatch):
        '''Run this before every test invocation'''
        self.client = mock.Mock()
        self.bodhi = bodhi_utils.BodhiUtils(self.client)
        self.client.query = mock.Mock(side_effect=self.mock_query)

    def test_basic(self):
        '''One update per build, mixed results'''
        updates, failures = self.bodhi.build2update(['foo-ok-1.2-3.fc20',
                                                     'bar-fail-1.8.0-4.fc20'])

        assert len(updates) == 1
        assert 'foo-ok-1.2-3.fc20' in updates
        assert (updates['foo-ok-1.2-3.fc20'] is
                self.requests['foo-ok-1.2-3.fc20'])

        assert len(failures) == 1
        assert 'bar-fail-1.8.0-4.fc20' in failures
        assert failures['bar-fail-1.8.0-4.fc20'] is None

    def test_raise(self):
        '''Invalid input params'''
        # 'builds' not iterable of strings
        with pytest.raises(exc.CheckbValueError):
            self.bodhi.build2update('foo-ok-1.2-3.fc20')

    def test_epoch(self):
        '''Should ignore epoch when asking about builds'''
        updates, failures = self.bodhi.build2update(['foo-ok-1:1.2-3.fc20',
                                                     'bar-ok-0:1.8.0-4.fc20'])

        assert not failures
        assert len(updates) == 2
        for update in updates.values():
            assert len(update['builds']) == 1
        assert (updates['foo-ok-1:1.2-3.fc20']['builds'][0]['nvr'] ==
                'foo-ok-1.2-3.fc20')
        assert (updates['bar-ok-0:1.8.0-4.fc20']['builds'][0]['nvr'] ==
                'bar-ok-1.8.0-4.fc20')

    def test_multi(self):
        '''Multiple builds in an update'''
        updates, failures = self.bodhi.build2update(['multi1-a-1.0-1.fc20',
                                                     'multi1-b-2.0-2.fc20',
                                                     'multi2-a-1.0-1.fc20',
                                                     'foo-fail-1.2-3.fc20'])

        assert len(updates) == 3
        assert 'multi1-a-1.0-1.fc20' in updates
        assert 'multi1-b-2.0-2.fc20' in updates
        assert (updates['multi1-a-1.0-1.fc20'] == updates['multi1-b-2.0-2.fc20'] ==
                self.requests['multi1-a-1.0-1.fc20'])
        # incomplete updates are allowed without strict=True
        assert 'multi2-a-1.0-1.fc20' in updates

        assert len(failures) == 1
        assert 'foo-fail-1.2-3.fc20' in failures
        assert failures['foo-fail-1.2-3.fc20'] is None

    def test_multi_strict(self):
        '''Multiple builds in an update with strict mode'''

        updates, failures = self.bodhi.build2update(['multi1-a-1.0-1.fc20',
                                                     'multi1-b-2.0-2.fc20',
                                                     'multi2-a-1.0-1.fc20',
                                                     'foo-fail-1.2-3.fc20'],
                                                    strict=True)

        assert len(updates) == 2
        assert 'multi1-a-1.0-1.fc20' in updates
        assert 'multi1-b-2.0-2.fc20' in updates
        assert (updates['multi1-a-1.0-1.fc20'] == updates['multi1-b-2.0-2.fc20'] ==
                self.requests['multi1-a-1.0-1.fc20'])

        assert len(failures) == 2
        assert 'multi2-a-1.0-1.fc20' in failures
        assert (failures['multi2-a-1.0-1.fc20'] is
                self.requests['multi2-a-1.0-1.fc20'])
        assert 'foo-fail-1.2-3.fc20' in failures
        assert failures['foo-fail-1.2-3.fc20'] is None

    def test_more_requests(self):
        '''Making multiple calls to Bodhi'''

        # decrease the request size to make sure we make several calls
        self.bodhi._MULTICALL_REQUEST_SIZE = 2

        updates, failures = self.bodhi.build2update(['multi1-a-1.0-1.fc20',
                                                     'multi1-b-2.0-2.fc20',
                                                     'multi2-a-1.0-1.fc20',
                                                     'foo-fail-1.2-3.fc20'])

        assert len(updates) == 3
        assert 'multi1-a-1.0-1.fc20' in updates
        assert 'multi1-b-2.0-2.fc20' in updates
        assert (updates['multi1-a-1.0-1.fc20'] == updates['multi1-b-2.0-2.fc20'] ==
                self.requests['multi1-a-1.0-1.fc20'])
        # incomplete updates are allowed without strict=True
        assert 'multi2-a-1.0-1.fc20' in updates

        assert len(failures) == 1
        assert 'foo-fail-1.2-3.fc20' in failures
        assert failures['foo-fail-1.2-3.fc20'] is None

    def test_more_requests_efficient(self):
        '''Builds from already received updates should be excluded from future calls'''

        # decrease the request size to make sure we make several calls
        self.bodhi._MULTICALL_REQUEST_SIZE = 1

        updates, failures = self.bodhi.build2update(['multi1-a-1.0-1.fc20',
                                                     'multi1-b-2.0-2.fc20',
                                                     'multi2-a-1.0-1.fc20',
                                                     'foo-fail-1.2-3.fc20'])

        calls = self.client.query.call_args_list
        # 3 calls, before one of multi1 packages should be skipped
        assert len(calls) == 3

        assert len(updates) == 3
        assert 'multi1-a-1.0-1.fc20' in updates
        assert 'multi1-b-2.0-2.fc20' in updates
        assert (updates['multi1-a-1.0-1.fc20'] == updates['multi1-b-2.0-2.fc20'] ==
                self.requests['multi1-a-1.0-1.fc20'])
        # incomplete updates are allowed without strict=True
        assert 'multi2-a-1.0-1.fc20' in updates

        assert len(failures) == 1
        assert 'foo-fail-1.2-3.fc20' in failures
        assert failures['foo-fail-1.2-3.fc20'] is None
