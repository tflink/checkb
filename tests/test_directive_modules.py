# -*- coding: utf-8 -*-
# Copyright 2009-2014, Red Hat, Inc.
# License: GPL-2.0+ <http://spdx.org/licenses/GPL-2.0+>
# See the LICENSE file for more details on Licensing


import pytest
import imp
import os
from glob import glob

from checkb import directives



class TestDirectives():
    @classmethod
    def setup_class(cls):
        cls.directive_modules = []

        # find all directive modules in checkb.directives directory
        for filepath in glob(os.path.join(os.path.dirname(directives.__file__),
                                          '*.py')):
            if 'directive' in os.path.basename(filepath):
                real_name = os.path.basename(filepath)[:-len('.py')]
                cls.directive_modules.append((real_name, filepath))

    def test_directive_class_var_exists(self):
        """Every directive module must contain a global variable named
        `directive_class` that contains classname of directive class
        """
        for module in self.directive_modules:
            loaded = imp.load_source(*module)
            class_name = getattr(loaded, 'directive_class')
            instance = getattr(loaded, class_name)()

            assert class_name == instance.__class__.__name__

    def test_directive_class_inherits_from_base(self):
        for module in self.directive_modules:
            loaded = imp.load_source(*module)
            class_name = getattr(loaded, 'directive_class')
            directive_class = getattr(loaded, class_name)

            assert issubclass(directive_class, directives.BaseDirective)

    def test_directive_class_process_method_exists(self):
        for module in self.directive_modules:
            loaded = imp.load_source(*module)
            class_name = getattr(loaded, 'directive_class')
            instance = getattr(loaded, class_name)()

            process_method = getattr(instance, "process", None)

            assert process_method is not None
            assert hasattr(process_method, '__call__')