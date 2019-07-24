# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing

from checkb.directives import BaseDirective

class StubDirective(BaseDirective):
    def process(self, command, params, arg_data):
        return "this is just a stub"
