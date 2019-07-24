# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

import pytest
import mock
from io import StringIO
import sys

from checkb.directives import yumrepoinfo_directive
from checkb.exceptions import CheckbDirectiveError

from checkb.ext.fedora import yumrepoinfo

from .test_yumrepoinfo import TEST_CONF


class TestYumrepoinfoDirective(object):

    @classmethod
    @pytest.fixture(autouse=True)
    def setup_class(cls, tmpdir, monkeypatch):
        '''One-time class initialization'''
        monkeypatch.setattr(yumrepoinfo.YumRepoInfo, '_switch_to_mirror', mock.Mock())
        # create YumRepoInfo initialized with TEST_CONF
        cls.temp_conf = tmpdir.join("functest_yumrepoinfo.conf")
        cls.temp_conf.write(TEST_CONF)

    def test_missing_kojitag(self):
        directive = yumrepoinfo_directive.YumrepoinfoDirective(filelist=[self.temp_conf.strpath])
        ref_input = {"arch": "x86_64"}

        with pytest.raises(CheckbDirectiveError):
            directive.process(ref_input, None)

    def test_missing_arch(self):
        directive = yumrepoinfo_directive.YumrepoinfoDirective(filelist=[self.temp_conf.strpath])
        ref_input = {"koji_tag": "rawhide"}

        with pytest.raises(CheckbDirectiveError):
            directive.process(ref_input, None)

    def test_pending(self):
        directive = yumrepoinfo_directive.YumrepoinfoDirective(filelist=[self.temp_conf.strpath])
        ref_input = {"koji_tag": "f20-pending", "arch": "x86_64"}

        output = directive.process(ref_input, None)

        assert output == {"f20": {"x86_64": "http://download.fedoraproject.org/pub/fedora/linux/releases/20/Everything/x86_64/os"}}

    def test_rawhide(self):
        directive = yumrepoinfo_directive.YumrepoinfoDirective(filelist=[self.temp_conf.strpath])
        ref_input = {"koji_tag": "rawhide", "arch": "x86_64"}

        output = directive.process(ref_input, None)

        assert output == {"rawhide": {"x86_64": "http://download.fedoraproject.org/pub/fedora/linux/development/rawhide/x86_64/os"}}

    def test_bad_kojitag(self):
        directive = yumrepoinfo_directive.YumrepoinfoDirective(filelist=[self.temp_conf.strpath])
        ref_input = {"koji_tag": "my random tag"}

        with pytest.raises(CheckbDirectiveError):
            directive.process(ref_input, None)

    def test_repo_path(self):

        directive = yumrepoinfo_directive.YumrepoinfoDirective(filelist=[self.temp_conf.strpath])
        ref_input = {"koji_tag": "f20-updates", "arch": "x86_64"}

        output = directive.process(ref_input, None)

        assert output == {
            "f20": {"x86_64": "http://download.fedoraproject.org/pub/fedora/linux/releases/20/Everything/x86_64/os"},
            "f20-updates": {"x86_64": "http://download.fedoraproject.org/pub/fedora/linux/updates/20/x86_64"},
            }

    def test_use_arch(self, monkeypatch):
        """Make sure that the arch passed in as an arg is used to create the
        yumrepoinfo object instead of falling back to the default system arch"""
        ref_arch = 'i386'
        repoinfo = yumrepoinfo.YumRepoInfo(filelist=[], arch='x86_64')
        if (sys.version_info >= (3, 2)):
            repoinfo.parser.read_file(StringIO(TEST_CONF))
        else:
            repoinfo.parser.readfp(StringIO(TEST_CONF))

        stub_getrepoinfo = mock.MagicMock(return_value=repoinfo)
        monkeypatch.setattr(yumrepoinfo, 'get_yumrepoinfo', stub_getrepoinfo)

        # don't set the repoinfo object, we've stubbed out the code that would
        # hit the filesystem, so it's not a risk here
        directive = yumrepoinfo_directive.YumrepoinfoDirective()
        ref_input = {"koji_tag": "f20-updates", "arch": ref_arch}

        directive.process(ref_input, None)

        # check the first arg of the first call to the stub object
        assert stub_getrepoinfo.call_args_list[0][0][0] == ref_arch

    def test_only_meta_arches(self):
        directive = yumrepoinfo_directive.YumrepoinfoDirective(filelist=[self.temp_conf.strpath])
        ref_input = {"koji_tag": "f20", "arch": ["src", "noarch"]}

        with pytest.raises(CheckbDirectiveError):
            directive.process(ref_input, None)

    def test_one_base_arch(self):
        directive = yumrepoinfo_directive.YumrepoinfoDirective(filelist=[self.temp_conf.strpath])
        ref_input = {"koji_tag": "f20", "arch": "x86_64"}

        output = directive.process(ref_input, None)

        assert output == {
            "f20": {"x86_64": "http://download.fedoraproject.org/pub/fedora/linux/releases/20/"
                              "Everything/x86_64/os"}
        }

    def test_one_arch_as_list(self):
        directive = yumrepoinfo_directive.YumrepoinfoDirective(filelist=[self.temp_conf.strpath])
        ref_input = {"koji_tag": "f20", "arch": ["x86_64"]}

        output = directive.process(ref_input, None)

        assert output == {
            "f20": {"x86_64": "http://download.fedoraproject.org/pub/fedora/linux/releases/20/Everything/x86_64/os"}
            }

    def test_base_meta_arch(self):
        directive = yumrepoinfo_directive.YumrepoinfoDirective(filelist=[self.temp_conf.strpath])
        ref_input = {"koji_tag": "f20", "arch": ["src", "noarch", "x86_64"]}

        output = directive.process(ref_input, None)

        assert output == {
            "f20": {"x86_64": "http://download.fedoraproject.org/pub/fedora/linux/releases/20/Everything/x86_64/os"}
            }

    def test_multiple_base_arches(self):
        directive = yumrepoinfo_directive.YumrepoinfoDirective(filelist=[self.temp_conf.strpath])
        ref_input = {"koji_tag": "f20", "arch": ["i386", "x86_64"]}

        output = directive.process(ref_input, None)

        assert output == {
            "f20": {
                "i386": "http://download.fedoraproject.org/pub/fedora-secondary/releases/20/"
                        "Everything/i386/os",
                "x86_64": "http://download.fedoraproject.org/pub/fedora/linux/releases/20/"
                          "Everything/x86_64/os"
            }
        }

    def test_multiple_base_meta_arches(self):
        directive = yumrepoinfo_directive.YumrepoinfoDirective(filelist=[self.temp_conf.strpath])
        ref_input = {"koji_tag": "f20", "arch": ["src", "i386", "x86_64"]}

        output = directive.process(ref_input, None)

        assert output == {
            "f20": {
                "i386": "http://download.fedoraproject.org/pub/fedora-secondary/releases/20/"
                        "Everything/i386/os",
                "x86_64": "http://download.fedoraproject.org/pub/fedora/linux/releases/20/"
                          "Everything/x86_64/os"
            }
        }
